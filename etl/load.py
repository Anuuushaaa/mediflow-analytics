"""
MediFlow Analytics — Load Layer (Phase 6)

Loads cleaned DataFrames into PostgreSQL via SQLAlchemy.

Strategy: TRUNCATE + RELOAD each run (chosen for this dev/portfolio
project for simplicity and determinism). In a real production system
with continuously-arriving data, an UPSERT/MERGE strategy would be
preferred instead, since truncating a live table causes a brief
window of missing data for anyone querying it and discards row-level
history. That tradeoff is a good interview talking point.

The entire load runs inside ONE database transaction: if any table
fails to load, ALL changes roll back, leaving the database in its
previous good state rather than a half-populated one (this is the
"Atomicity" in ACID).

Load order matters even with truncate+reload, because foreign keys
require parent rows (patients, doctors) to exist before child rows
(appointments, admissions, etc.) can reference them.

Usage:
    from etl.load import load_all
    load_all(clean_dataframes)
"""

import logging
import os
from pathlib import Path

import pandas as pd
import yaml
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger("etl.load")

# Load order respects FK dependencies: parents before children
LOAD_ORDER = [
    "patients",
    "doctors",
    "appointments",
    "admissions",
    "lab_results",
    "pharmacy",
    "billing",
    "insurance_claims",
]

# Columns to actually persist per table — excludes derived/analysis-only
# columns (age, age_group, length_of_stay_days, revenue_category) that
# don't exist in schema.sql. Those are recomputed on demand by SQL
# analytics (Phase 7) or BI tools, not duplicated into the database
# (this itself is a normalization principle: don't store what you can derive).
TABLE_COLUMNS = {
    "patients": ["patient_id", "first_name", "last_name", "date_of_birth", "gender",
                 "phone_number", "email", "registration_date", "blood_group", "city"],
    "doctors": ["doctor_id", "first_name", "last_name", "department", "specialization",
                "years_experience", "phone_number", "hire_date"],
    "appointments": ["appointment_id", "patient_id", "doctor_id", "appointment_date",
                      "appointment_time", "status", "reason_for_visit"],
    "admissions": ["admission_id", "patient_id", "doctor_id", "department",
                    "admission_date", "discharge_date", "diagnosis", "room_type"],
    "lab_results": ["lab_id", "patient_id", "doctor_id", "test_name", "test_date",
                      "result_status", "turnaround_hours"],
    "pharmacy": ["prescription_id", "patient_id", "doctor_id", "medication_name",
                  "quantity", "unit_cost", "prescribed_date"],
    "billing": ["bill_id", "patient_id", "admission_id", "bill_date", "amount",
                 "payment_status", "payment_method"],
    "insurance_claims": ["claim_id", "bill_id", "patient_id", "insurance_provider",
                           "claim_amount", "claim_status", "claim_date"],
}


class LoadError(Exception):
    """Raised when the load transaction fails and is rolled back."""
    pass


def get_engine(config_path: str = "config/config.yaml"):
    """Build a SQLAlchemy engine from config.yaml (non-secret) + .env (secret)."""
    load_dotenv()

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    db_cfg = config["database"]
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")

    if not user or not password:
        raise LoadError(
            "DB_USER / DB_PASSWORD not found in environment. "
            "Check that .env exists and is non-empty."
        )

    connection_url = URL.create(
        drivername="postgresql+psycopg2",
        username=user,
        password=password,
        host=db_cfg["host"],
        port=int(db_cfg["port"]),
        database=db_cfg["name"],
    )

    return create_engine(connection_url)


def load_all(clean: dict, config_path: str = "config/config.yaml") -> None:
    """
    Truncate and reload all 8 tables inside a single transaction.
    Raises LoadError (and rolls back) if any table fails to load.
    """
    logger.info("=" * 70)
    logger.info("Starting load into PostgreSQL")
    logger.info("=" * 70)

    engine = get_engine(config_path)

    try:
        with engine.begin() as conn:  # engine.begin() = one transaction, auto-commits on success, auto-rollback on exception
            # Truncate in REVERSE load order (children before parents) to
            # respect FK constraints during the wipe.
            logger.info("Truncating existing tables (reverse FK order)...")
            for table in reversed(LOAD_ORDER):
                conn.execute(text(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE"))

            # Load in FORWARD order (parents before children)
            for table in LOAD_ORDER:
                df = clean[table][TABLE_COLUMNS[table]].copy()

                # admission_id in billing can be NaN -> must become SQL NULL, not "nan"
                df = df.where(pd.notnull(df), None)

                df.to_sql(table, con=conn, if_exists="append", index=False, method="multi", chunksize=1000)
                logger.info(f"  -> loaded {len(df):,} rows into {table}")

        logger.info("Load complete — transaction committed successfully")

    except SQLAlchemyError as e:
        logger.error(f"Load FAILED — transaction rolled back. Reason: {e}")
        raise LoadError(f"Load failed and was rolled back: {e}") from e


def verify_load(clean: dict, config_path: str = "config/config.yaml") -> None:
    """Post-load sanity check: row count in DB should match rows we sent."""
    engine = get_engine(config_path)
    logger.info("Verifying row counts (expected vs. actual in DB)...")

    all_match = True
    with engine.connect() as conn:
        for table in LOAD_ORDER:
            expected = len(clean[table])
            actual = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            status = "OK" if expected == actual else "MISMATCH"
            if status == "MISMATCH":
                all_match = False
            logger.info(f"  {table:20s} expected={expected:>7,}  actual={actual:>7,}  [{status}]")

    if not all_match:
        raise LoadError("Row count verification failed — see log for mismatched table(s)")
    logger.info("Row count verification passed — all tables match")


if __name__ == "__main__":
    from etl.extract import extract_all
    from etl.transform import transform_all

    raw = extract_all()
    clean = transform_all(raw)
    load_all(clean)
    verify_load(clean)