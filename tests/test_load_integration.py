
"""
PostgreSQL integration tests for MediFlow Analytics.

These tests connect ONLY to mediflow_analytics_test.
They never connect to the main analytics database.

Run explicitly:
    python -m pytest tests/test_load_integration.py -v
"""

import os
from unittest.mock import patch

import pandas as pd
import pytest
pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_INTEGRATION_TESTS") != "1",
    reason="Requires explicit opt-in and a dedicated PostgreSQL test database",
)
from sqlalchemy import text

from etl.load import (
    LOAD_ORDER,
    TABLE_COLUMNS,
    LoadError,
    get_engine,
    load_all,
)

TEST_CONFIG = "config/test_config.yaml"
TEST_DATABASE = "mediflow_analytics_test"


@pytest.fixture
def test_engine():
    """Connect to the isolated PostgreSQL test database."""
    engine = get_engine(TEST_CONFIG)

    try:
        with engine.connect() as conn:
            actual_database = conn.execute(
                text("SELECT current_database()")
            ).scalar_one()

        if actual_database != TEST_DATABASE:
            pytest.fail(
                f"SAFETY STOP: Expected {TEST_DATABASE}, "
                f"connected to {actual_database}"
            )

        yield engine

    finally:
        engine.dispose()


@pytest.fixture
def clean_data():
    """Create valid records for the eight hospital tables."""
    records = {
        "patients": {
            "patient_id": 1,
            "first_name": "Test",
            "last_name": "Patient",
            "date_of_birth": "1995-01-01",
            "gender": "Female",
            "phone_number": "9111111111",
            "email": "test@example.com",
            "registration_date": "2024-01-01",
            "blood_group": "A+",
            "city": "Kochi",
        },
        "doctors": {
            "doctor_id": 1,
            "first_name": "Test",
            "last_name": "Doctor",
            "department": "Cardiology",
            "specialization": "Heart",
            "years_experience": 10,
            "phone_number": "8111111111",
            "hire_date": "2015-01-01",
        },
        "appointments": {
            "appointment_id": 1,
            "patient_id": 1,
            "doctor_id": 1,
            "appointment_date": "2024-01-10",
            "appointment_time": "09:00",
            "status": "Completed",
            "reason_for_visit": "Checkup",
        },
        "admissions": {
            "admission_id": 1,
            "patient_id": 1,
            "doctor_id": 1,
            "department": "Cardiology",
            "admission_date": "2024-01-11",
            "discharge_date": "2024-01-13",
            "diagnosis": "Observation",
            "room_type": "General",
        },
        "lab_results": {
            "lab_id": 1,
            "patient_id": 1,
            "doctor_id": 1,
            "test_name": "Blood Test",
            "test_date": "2024-01-10",
            "result_status": "Normal",
            "turnaround_hours": 4.0,
        },
        "pharmacy": {
            "prescription_id": 1,
            "patient_id": 1,
            "doctor_id": 1,
            "medication_name": "Test Medicine",
            "quantity": 2,
            "unit_cost": 10.0,
            "prescribed_date": "2024-01-10",
        },
        "billing": {
            "bill_id": 1,
            "patient_id": 1,
            "admission_id": 1,
            "bill_date": "2024-01-13",
            "amount": 100.0,
            "payment_status": "Paid",
            "payment_method": "Cash",
        },
        "insurance_claims": {
            "claim_id": 1,
            "bill_id": 1,
            "patient_id": 1,
            "insurance_provider": "Test Insurance",
            "claim_amount": 50.0,
            "claim_status": "Approved",
            "claim_date": "2024-01-14",
        },
    }

    return {
        table: pd.DataFrame(
            [records[table]],
            columns=TABLE_COLUMNS[table],
        )
        for table in LOAD_ORDER
    }


def test_successful_load_commits(test_engine, clean_data):
    """Successful loading should commit one row in every table."""
    load_all(clean_data, config_path=TEST_CONFIG)

    with test_engine.connect() as conn:
        for table in LOAD_ORDER:
            count = conn.execute(
                text(f"SELECT COUNT(*) FROM {table}")
            ).scalar_one()

            assert count == 1, f"{table} should contain one row"


def test_failed_verification_rolls_back(test_engine, clean_data):
    """
    A failed verification should preserve previously committed data.
    """
    # Establish a known committed baseline.
    load_all(clean_data, config_path=TEST_CONFIG)

    # Change a record so we can detect an unwanted commit.
    modified = {
        table: df.copy()
        for table, df in clean_data.items()
    }
    modified["patients"].loc[0, "first_name"] = "Changed"

    # Force verification to fail inside the active transaction.
    with patch(
        "etl.load._verify_counts",
        side_effect=LoadError("Simulated verification failure"),
    ):
        with pytest.raises(
            LoadError,
            match="Simulated verification failure",
        ):
            load_all(modified, config_path=TEST_CONFIG)

    # The original committed patient must still exist.
    with test_engine.connect() as conn:
        first_name = conn.execute(
            text(
                "SELECT first_name FROM patients "
                "WHERE patient_id = 1"
            )
        ).scalar_one()

        assert first_name == "Test"

        for table in LOAD_ORDER:
            count = conn.execute(
                text(f"SELECT COUNT(*) FROM {table}")
            ).scalar_one()

            assert count == 1, f"{table} changed after rollback"
