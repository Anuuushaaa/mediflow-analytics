
"""
MediFlow Analytics - PostgreSQL Load Layer.

Loads cleaned hospital datasets into PostgreSQL.

All truncation, insertion, and row-count verification happen
inside one database transaction.

If loading or verification fails, PostgreSQL rolls back
the entire transaction.
"""

import logging
import os

import pandas as pd
import yaml
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError


logger = logging.getLogger("etl.load")


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


TABLE_COLUMNS = {
    "patients": [
        "patient_id",
        "first_name",
        "last_name",
        "date_of_birth",
        "gender",
        "phone_number",
        "email",
        "registration_date",
        "blood_group",
        "city",
    ],
    "doctors": [
        "doctor_id",
        "first_name",
        "last_name",
        "department",
        "specialization",
        "years_experience",
        "phone_number",
        "hire_date",
    ],
    "appointments": [
        "appointment_id",
        "patient_id",
        "doctor_id",
        "appointment_date",
        "appointment_time",
        "status",
        "reason_for_visit",
    ],
    "admissions": [
        "admission_id",
        "patient_id",
        "doctor_id",
        "department",
        "admission_date",
        "discharge_date",
        "diagnosis",
        "room_type",
    ],
    "lab_results": [
        "lab_id",
        "patient_id",
        "doctor_id",
        "test_name",
        "test_date",
        "result_status",
        "turnaround_hours",
    ],
    "pharmacy": [
        "prescription_id",
        "patient_id",
        "doctor_id",
        "medication_name",
        "quantity",
        "unit_cost",
        "prescribed_date",
    ],
    "billing": [
        "bill_id",
        "patient_id",
        "admission_id",
        "bill_date",
        "amount",
        "payment_status",
        "payment_method",
    ],
    "insurance_claims": [
        "claim_id",
        "bill_id",
        "patient_id",
        "insurance_provider",
        "claim_amount",
        "claim_status",
        "claim_date",
    ],
}


class LoadError(Exception):
    """Raised when database loading or verification fails."""


def get_engine(config_path: str = "config/config.yaml"):
    """
    Create a PostgreSQL SQLAlchemy engine.

    Database settings come from config.yaml.
    Credentials come from environment variables.
    """
    load_dotenv()

    with open(config_path, "r", encoding="utf-8") as f:
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


def _verify_counts(conn, clean: dict) -> None:
    """
    Verify all eight table row counts.

    Uses the provided connection so verification can
    happen inside the active loading transaction.
    """
    logger.info("Verifying row counts...")

    for table in LOAD_ORDER:
        expected = len(clean[table])

        actual = conn.execute(
            text(f"SELECT COUNT(*) FROM {table}")
        ).scalar_one()

        if actual != expected:
            raise LoadError(
                f"Row count mismatch in {table}: "
                f"expected {expected:,}, found {actual:,}"
            )

        logger.info(
            "  %s: %s rows verified",
            table,
            f"{actual:,}",
        )

    logger.info("All table row counts verified successfully")


def load_all(
    clean: dict,
    config_path: str = "config/config.yaml",
) -> None:
    """
    Load all cleaned datasets in a single transaction.

    Operations:
    1. Validate the database connection for integration tests.
    2. Truncate existing tables.
    3. Insert cleaned data.
    4. Verify row counts.
    5. Commit only if everything succeeds.

    Any exception inside the transaction causes a rollback.
    """
    logger.info("Starting load into PostgreSQL")

    engine = get_engine(config_path)

    try:
        with engine.begin() as conn:

            # Safety check for integration test configuration.
            if os.path.basename(config_path) == "test_config.yaml":
                actual_database = conn.execute(
                    text("SELECT current_database()")
                ).scalar_one()

                if actual_database != "mediflow_analytics_test":
                    raise LoadError(
                        "SAFETY STOP: Integration test connected "
                        f"to unexpected database: {actual_database}"
                    )

            # Truncate existing data in reverse dependency order.
            for table in reversed(LOAD_ORDER):
                conn.execute(
                    text(
                        f"TRUNCATE TABLE {table} "
                        "RESTART IDENTITY CASCADE"
                    )
                )

            # Insert cleaned records.
            for table in LOAD_ORDER:
                df = clean[table][TABLE_COLUMNS[table]].copy()

                # Convert missing values into database NULLs.
                df = df.astype(object).where(
                    pd.notnull(df),
                    None,
                )

                df.to_sql(
                    table,
                    con=conn,
                    if_exists="append",
                    index=False,
                    method="multi",
                    chunksize=1000,
                )

                logger.info(
                    "  -> loaded %s rows into %s",
                    f"{len(df):,}",
                    table,
                )

            # Verify counts BEFORE the transaction commits.
            _verify_counts(conn, clean)

        # Reaching here means engine.begin() committed.
        logger.info(
            "Load complete - transaction committed successfully"
        )

    except (SQLAlchemyError, LoadError) as e:
        logger.error(
            "Load FAILED - transaction rolled back. Reason: %s",
            e,
        )

        raise LoadError(
            f"Load failed and was rolled back: {e}"
        ) from e

    finally:
        engine.dispose()


def verify_load(
    clean: dict,
    config_path: str = "config/config.yaml",
) -> None:
    """
    Optional standalone read-only verification.

    The main pipeline already verifies row counts
    inside load_all().
    """
    engine = get_engine(config_path)

    try:
        with engine.connect() as conn:
            _verify_counts(conn, clean)

        logger.info("Standalone row-count verification passed")

    except SQLAlchemyError as e:
        raise LoadError(
            f"Standalone verification failed: {e}"
        ) from e

    finally:
        engine.dispose()
