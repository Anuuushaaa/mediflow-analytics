
"""
MediFlow Analytics - Incremental PostgreSQL Load Layer.

Supports:
- Inserting new records
- Updating changed records
- Skipping unchanged records
- Preserving records absent from incoming data
- Transactional rollback on failure

The existing full-refresh loader remains available
through etl.load.load_all().
"""

import logging
import os

import pandas as pd
from sqlalchemy import MetaData, Table, text
from sqlalchemy.dialects.postgresql import insert

from etl.load import LOAD_ORDER, TABLE_COLUMNS, get_engine


logger = logging.getLogger("etl.incremental_load")


PRIMARY_KEYS = {
    "patients": "patient_id",
    "doctors": "doctor_id",
    "appointments": "appointment_id",
    "admissions": "admission_id",
    "lab_results": "lab_id",
    "pharmacy": "prescription_id",
    "billing": "bill_id",
    "insurance_claims": "claim_id",
}


class IncrementalLoadError(Exception):
    """Raised when incremental loading fails."""
    pass


def prepare_records(df, columns):
    """
    Convert a cleaned DataFrame into database-ready records.

    Handles:
    - Pandas missing values -> None
    - Pandas Timestamp -> Python datetime
    - NumPy scalar values -> Python native values
    """

    records_df = df[columns].copy()

    records_df = records_df.astype(object).where(
        pd.notnull(records_df),
        None,
    )

    records = records_df.to_dict(orient="records")

    for record in records:
        for column, value in record.items():

            if isinstance(value, pd.Timestamp):
                record[column] = value.to_pydatetime()

            elif hasattr(value, "item"):
                record[column] = value.item()

    return records


def upsert_table(conn, table, df, metadata):
    """
    Insert new records and update changed records.

    Uses PostgreSQL ON CONFLICT.

    Identical records are skipped.

    The caller manages the database transaction.

    Returns the number of inserted or updated records.
    """

    if table not in PRIMARY_KEYS:
        raise ValueError(
            f"Unknown table: {table}"
        )

    primary_key = PRIMARY_KEYS[table]
    columns = TABLE_COLUMNS[table]

    missing_columns = set(columns) - set(df.columns)

    if missing_columns:
        raise ValueError(
            f"{table}: missing columns "
            f"{sorted(missing_columns)}"
        )

    if df[primary_key].isna().any():
        raise ValueError(
            f"{table}: null primary keys detected"
        )

    if df[primary_key].duplicated().any():
        raise ValueError(
            f"{table}: duplicate primary keys detected"
        )

    if df.empty:
        logger.info(
            "%s: no incoming records",
            table,
        )
        return 0

    target = Table(
        table,
        metadata,
        autoload_with=conn,
    )

    records = prepare_records(
        df,
        columns,
    )

    affected_rows = 0

    batch_size = 500

    for start in range(0, len(records), batch_size):

        batch = records[
            start:start + batch_size
        ]

        statement = insert(target).values(batch)

        update_columns = {
            column: statement.excluded[column]
            for column in columns
            if column != primary_key
        }

        changed_conditions = [
            target.c[column].is_distinct_from(
                statement.excluded[column]
            )
            for column in update_columns
        ]

        from sqlalchemy import or_

        statement = statement.on_conflict_do_update(
            index_elements=[primary_key],
            set_=update_columns,
            where=or_(*changed_conditions),
        )

        result = conn.execute(statement)

        affected_rows += result.rowcount

    logger.info(
        "%s: %s records inserted or updated",
        table,
        affected_rows,
    )

    return affected_rows


def incremental_load_all(
    clean: dict,
    config_path: str = "config/config.yaml",
) -> None:
    """
    Incrementally load all eight datasets.

    All database writes occur inside one transaction.

    If any table fails, the entire transaction
    is rolled back.
    """

    logger.info(
        "Starting incremental ETL load"
    )

    missing_tables = set(LOAD_ORDER) - set(clean)

    if missing_tables:
        raise IncrementalLoadError(
            f"Missing datasets: {sorted(missing_tables)}"
        )

    # Validate all datasets before opening the transaction.
    for table in LOAD_ORDER:

        df = clean[table]
        primary_key = PRIMARY_KEYS[table]
        required_columns = TABLE_COLUMNS[table]

        missing_columns = set(required_columns) - set(df.columns)

        if missing_columns:
            raise IncrementalLoadError(
                f"{table}: missing columns "
                f"{sorted(missing_columns)}"
            )

        if df[primary_key].isna().any():
            raise IncrementalLoadError(
                f"{table}: null primary keys detected"
            )

        if df[primary_key].duplicated().any():
            raise IncrementalLoadError(
                f"{table}: duplicate primary keys detected"
            )

    engine = get_engine(config_path)

    try:
        with engine.begin() as conn:

            # Integration test database safety check.
            if os.path.basename(config_path) == "test_config.yaml":

                database = conn.execute(
                    text("SELECT current_database()")
                ).scalar_one()

                if database != "mediflow_analytics_test":
                    raise IncrementalLoadError(
                        "SAFETY STOP: Integration test "
                        f"connected to unexpected database: {database}"
                    )

            metadata = MetaData()

            total_affected = 0

            for table in LOAD_ORDER:

                logger.info(
                    "Processing table: %s",
                    table,
                )

                affected = upsert_table(
                    conn=conn,
                    table=table,
                    df=clean[table],
                    metadata=metadata,
                )

                total_affected += affected

            logger.info(
                "All eight tables processed"
            )

        logger.info(
            "Incremental load committed successfully"
        )

        logger.info(
            "Total inserted or updated records: %s",
            total_affected,
        )

    except Exception as exc:

        logger.exception(
            "Incremental load failed. "
            "Database transaction rolled back."
        )

        raise IncrementalLoadError(
            f"Incremental load failed: {exc}"
        ) from exc

    finally:
        engine.dispose()
