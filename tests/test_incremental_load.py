
"""
Tests for MediFlow incremental PostgreSQL upserts.

Uses the isolated mediflow_analytics_test database.
All changes are rolled back after the test.
"""

import pandas as pd
import pytest
from sqlalchemy import MetaData, text

from etl.load import get_engine
from etl.incremental_load import upsert_table
from etl.incremental_load import incremental_load_all, IncrementalLoadError


@pytest.fixture
def test_connection():
    engine = get_engine("config/test_config.yaml")

    connection = engine.connect()

    try:
        database = connection.execute(
            text("SELECT current_database()")
        ).scalar_one()

        if database != "mediflow_analytics_test":
            raise RuntimeError(
                f"Unsafe test database: {database}"
            )

        transaction = connection.begin_nested()

        yield connection

        transaction.rollback()

    finally:
        connection.close()
        engine.dispose()


def test_incremental_upsert_is_idempotent(test_connection):
    """
    First run inserts a record.
    Second run skips the identical record.
    """

    patient = pd.DataFrame([
        {
            "patient_id": 999999,
            "first_name": "Incremental",
            "last_name": "Test",
            "date_of_birth": "2000-01-01",
            "gender": "Female",
            "phone_number": "9999999999",
            "email": "incremental.test@example.com",
            "registration_date": "2026-01-01",
            "blood_group": "O+",
            "city": "Kochi",
        }
    ])

    metadata = MetaData()

    first_result = upsert_table(
        conn=test_connection,
        table="patients",
        df=patient,
        metadata=metadata,
    )

    second_result = upsert_table(
        conn=test_connection,
        table="patients",
        df=patient,
        metadata=metadata,
    )

    count = test_connection.execute(
        text(
            "SELECT COUNT(*) FROM patients "
            "WHERE patient_id = 999999"
        )
    ).scalar_one()

    assert first_result == 1
    assert second_result == 0
    assert count == 1

def test_incremental_upsert_updates_changed_record(test_connection):
    """
    Verify that a changed record is updated,
    not duplicated.
    """

    patient = pd.DataFrame([
        {
            "patient_id": 999998,
            "first_name": "Incremental",
            "last_name": "UpdateTest",
            "date_of_birth": "2000-01-01",
            "gender": "Female",
            "phone_number": "9999999998",
            "email": "update.test@example.com",
            "registration_date": "2026-01-01",
            "blood_group": "O+",
            "city": "Kochi",
        }
    ])

    metadata = MetaData()

    # Insert the original record.
    first_result = upsert_table(
        conn=test_connection,
        table="patients",
        df=patient,
        metadata=metadata,
    )

    # Change the patient's city.
    patient.loc[0, "city"] = "Bangalore"

    # Upsert the changed record.
    second_result = upsert_table(
        conn=test_connection,
        table="patients",
        df=patient,
        metadata=metadata,
    )

    result = test_connection.execute(
        text(
            "SELECT city FROM patients "
            "WHERE patient_id = 999998"
        )
    ).scalar_one()

    count = test_connection.execute(
        text(
            "SELECT COUNT(*) FROM patients "
            "WHERE patient_id = 999998"
        )
    ).scalar_one()

    assert first_result == 1
    assert second_result == 1
    assert result == "Bangalore"
    assert count == 1

def test_incremental_upsert_rolls_back_on_failure(test_connection):
    """
    Verify that a failed database operation rolls back
    earlier successful changes in the same transaction.
    """

    patient = pd.DataFrame([
        {
            "patient_id": 999997,
            "first_name": "Rollback",
            "last_name": "Test",
            "date_of_birth": "2000-01-01",
            "gender": "Female",
            "phone_number": "9999999997",
            "email": "rollback.test@example.com",
            "registration_date": "2026-01-01",
            "blood_group": "O+",
            "city": "Kochi",
        }
    ])

    # Start a nested transaction for this test.
    savepoint = test_connection.begin_nested()

    try:
        # First operation: valid insertion.
        upsert_table(
            conn=test_connection,
            table="patients",
            df=patient,
            metadata=MetaData(),
        )

        # Second operation: invalid insertion.
        # Negative experience violates the doctors table constraint.
        invalid_doctor = pd.DataFrame([
            {
                "doctor_id": 999997,
                "first_name": "Invalid",
                "last_name": "Doctor",
                "department": "Cardiology",
                "specialization": "Cardiology",
                "years_experience": -5,
                "phone_number": "9999999996",
                "hire_date": "2020-01-01",
            }
        ])

        with pytest.raises(Exception):
            upsert_table(
                conn=test_connection,
                table="doctors",
                df=invalid_doctor,
                metadata=MetaData(),
            )

    finally:
        # Roll back both operations.
        savepoint.rollback()

    # Verify the earlier patient insertion was also undone.
    count = test_connection.execute(
        text(
            "SELECT COUNT(*) FROM patients "
            "WHERE patient_id = 999997"
        )
    ).scalar_one()

    assert count == 0

def test_incremental_load_all_rolls_back_on_failure(monkeypatch):
    """
    Verify that incremental_load_all automatically rolls back
    earlier table writes when a later table fails.

    Uses the isolated PostgreSQL test database.
    """

    from etl.load import LOAD_ORDER, TABLE_COLUMNS
    import etl.incremental_load as incremental_module

    original_get_engine = incremental_module.get_engine
    engine = original_get_engine("config/test_config.yaml")

    try:
        with engine.connect() as conn:
            database = conn.execute(
                text("SELECT current_database()")
            ).scalar_one()

            assert database == "mediflow_analytics_test"

            # Use a unique test ID and ensure it is absent.
            test_patient_id = 999996

            existing = conn.execute(
                text(
                    "SELECT COUNT(*) FROM patients "
                    "WHERE patient_id = :patient_id"
                ),
                {"patient_id": test_patient_id},
            ).scalar_one()

            assert existing == 0

        # Build empty DataFrames for all eight tables.
        clean = {
            table: pd.DataFrame(columns=TABLE_COLUMNS[table])
            for table in LOAD_ORDER
        }

        # Valid patient: processed first.
        clean["patients"] = pd.DataFrame([
            {
                "patient_id": test_patient_id,
                "first_name": "Atomic",
                "last_name": "Rollback",
                "date_of_birth": "2000-01-01",
                "gender": "Female",
                "phone_number": "9999999995",
                "email": "atomic.rollback@example.com",
                "registration_date": "2026-01-01",
                "blood_group": "O+",
                "city": "Kochi",
            }
        ])

        # Invalid doctor: processed after patients.
        clean["doctors"] = pd.DataFrame([
            {
                "doctor_id": 999996,
                "first_name": "Invalid",
                "last_name": "Doctor",
                "department": "Cardiology",
                "specialization": "Cardiology",
                "years_experience": -5,
                "phone_number": "9999999994",
                "hire_date": "2020-01-01",
            }
        ])

        # Force the loader to use the test database.
        monkeypatch.setattr(
            incremental_module,
            "get_engine",
            lambda config_path: engine,
        )

        # The invalid doctor must cause the entire load to fail.
        with pytest.raises(IncrementalLoadError):
            incremental_load_all(
                clean,
                config_path="config/test_config.yaml",
            )

        # Confirm the valid patient was also rolled back.
        with engine.connect() as conn:
            count = conn.execute(
                text(
                    "SELECT COUNT(*) FROM patients "
                    "WHERE patient_id = :patient_id"
                ),
                {"patient_id": test_patient_id},
            ).scalar_one()

        assert count == 0

    finally:
        engine.dispose()

def test_incremental_upsert_preserves_missing_records(test_connection):
    """
    Verify that an existing database record is preserved
    when it is absent from a later incoming batch.
    """

    original_patient = pd.DataFrame([
        {
            "patient_id": 999995,
            "first_name": "Preserved",
            "last_name": "Patient",
            "date_of_birth": "2000-01-01",
            "gender": "Female",
            "phone_number": "9999999993",
            "email": "preserved.patient@example.com",
            "registration_date": "2026-01-01",
            "blood_group": "O+",
            "city": "Kochi",
        }
    ])

    # Insert the original patient.
    first_result = upsert_table(
        conn=test_connection,
        table="patients",
        df=original_patient,
        metadata=MetaData(),
    )

    # Simulate a later source batch without this patient.
    empty_batch = original_patient.iloc[0:0].copy()

    second_result = upsert_table(
        conn=test_connection,
        table="patients",
        df=empty_batch,
        metadata=MetaData(),
    )

    # The original record should still exist.
    result = test_connection.execute(
        text(
            "SELECT first_name, city "
            "FROM patients "
            "WHERE patient_id = :patient_id"
        ),
        {"patient_id": 999995},
    ).one()

    assert first_result == 1
    assert second_result == 0
    assert result.first_name == "Preserved"
    assert result.city == "Kochi"

def test_incremental_upsert_handles_nulls_and_dates(test_connection):
    """
    Verify that Pandas timestamps and nullable fields
    are handled correctly during PostgreSQL upserts.
    """

    patient = pd.DataFrame([
        {
            "patient_id": 999994,
            "first_name": "Nullable",
            "last_name": "Test",
            "date_of_birth": pd.Timestamp("2000-01-01"),
            "gender": "Female",
            "phone_number": None,
            "email": None,
            "registration_date": pd.Timestamp("2026-01-01"),
            "blood_group": None,
            "city": "Kochi",
        }
    ])

    # Insert the patient with nullable fields.
    first_result = upsert_table(
        conn=test_connection,
        table="patients",
        df=patient,
        metadata=MetaData(),
    )

    # Verify dates and NULL values in PostgreSQL.
    result = test_connection.execute(
        text(
            "SELECT date_of_birth, registration_date, "
            "phone_number, email, blood_group "
            "FROM patients "
            "WHERE patient_id = :patient_id"
        ),
        {"patient_id": 999994},
    ).one()

    assert first_result == 1
    assert str(result.date_of_birth) == "2000-01-01"
    assert str(result.registration_date) == "2026-01-01"
    assert result.phone_number is None
    assert result.email is None
    assert result.blood_group is None

    # Running the identical record again should do nothing.
    second_result = upsert_table(
        conn=test_connection,
        table="patients",
        df=patient,
        metadata=MetaData(),
    )

    assert second_result == 0
