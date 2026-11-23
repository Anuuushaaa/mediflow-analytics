
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
import pendulum

from airflow import DAG
from airflow.operators.python import PythonOperator
from sqlalchemy import text


# --------------------------------------------------
# Project configuration
# --------------------------------------------------

PROJECT_DIR = Path("/opt/mediflow")
CONFIG_PATH = PROJECT_DIR / "config" / "docker_config.yaml"
DATABASE_NAME = "mediflow_docker"

EXPECTED_TABLES = {
    "patients": 5000,
    "doctors": 150,
    "appointments": 14581,
    "admissions": 2921,
    "lab_results": 7849,
    "pharmacy": 9842,
    "billing": 5754,
    "insurance_claims": 2873,
}


# --------------------------------------------------
# Task 1: Check PostgreSQL connection
# --------------------------------------------------

def check_database_connection():
    from etl.load import get_engine

    engine = get_engine(str(CONFIG_PATH))

    try:
        with engine.connect() as connection:
            database = connection.execute(
                text("SELECT current_database()")
            ).scalar_one()

            if database != DATABASE_NAME:
                raise RuntimeError(
                    f"Unexpected database: {database}. "
                    f"Expected: {DATABASE_NAME}"
                )

            print(f"PASS: Connected to {database}")

    finally:
        engine.dispose()


# --------------------------------------------------
# Task 2: Execute MediFlow ETL
# --------------------------------------------------

def run_mediflow_etl():
    environment = os.environ.copy()
    environment["MEDIFLOW_CONFIG"] = str(CONFIG_PATH)

    print("Starting MediFlow ETL pipeline...")

    subprocess.run(
        ["python", "run_pipeline.py"],
        cwd=str(PROJECT_DIR),
        env=environment,
        check=True,
    )

    print("PASS: MediFlow ETL completed successfully.")


# --------------------------------------------------
# Task 3: Verify PostgreSQL records
# --------------------------------------------------

def verify_loaded_records():
    from etl.load import get_engine

    engine = get_engine(str(CONFIG_PATH))

    try:
        with engine.connect() as connection:

            database = connection.execute(
                text("SELECT current_database()")
            ).scalar_one()

            if database != DATABASE_NAME:
                raise RuntimeError(
                    f"Unexpected database: {database}"
                )

            total_rows = 0

            for table_name, expected_count in EXPECTED_TABLES.items():

                actual_count = connection.execute(
                    text(f"SELECT COUNT(*) FROM {table_name}")
                ).scalar_one()

                if actual_count != expected_count:
                    raise RuntimeError(
                        f"FAIL: {table_name} - "
                        f"expected {expected_count}, "
                        f"got {actual_count}"
                    )

                print(
                    f"PASS: {table_name} "
                    f"({actual_count}/{expected_count} records)"
                )

                total_rows += actual_count

            expected_total = sum(EXPECTED_TABLES.values())

            if total_rows != expected_total:
                raise RuntimeError(
                    f"Total row count mismatch: "
                    f"expected {expected_total}, got {total_rows}"
                )

            print("All 8 tables verified successfully.")
            print(f"Total records verified: {total_rows}")

    finally:
        engine.dispose()


# --------------------------------------------------
# Airflow configuration
# --------------------------------------------------

default_args = {
    "owner": "mediflow",
    "retries": 2,
    "retry_delay": timedelta(minutes=1),
}



with DAG(
    dag_id="mediflow_etl",
    description="MediFlow Analytics daily ETL orchestration",
    start_date=pendulum.datetime(
        2026, 11, 24, 0, 0, tz="Asia/Kolkata"
    ),
    schedule_interval="0 2 * * *",
    catchup=False,
    default_args=default_args,
    max_active_runs=1,
    tags=["mediflow", "etl", "data-engineering"],
) as dag:


    check_database = PythonOperator(
        task_id="check_database_connection",
        python_callable=check_database_connection,
    )

    run_etl = PythonOperator(
        task_id="run_mediflow_etl",
        python_callable=run_mediflow_etl,
    )

    verify_records = PythonOperator(
        task_id="verify_loaded_records",
        python_callable=verify_loaded_records,
    )

    check_database >> run_etl >> verify_records
