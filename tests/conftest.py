"""
Shared pytest fixtures — small, hand-crafted DataFrames that deliberately
include the SAME categories of data quality issues we seed in the real
generator (Phase 2), so tests exercise real logic without needing the
full 5,000-row dataset or a live database.
"""

import pandas as pd
import pytest


@pytest.fixture
def sample_patients():
    """6 patients: 1 clean duplicate pair, 1 messy-gender row, 1 missing phone."""
    return pd.DataFrame({
        "patient_id": [1, 2, 3, 4, 5, 6],
        "first_name": ["Alice", "Bob", "Alice", "Carol", "Dave", "Eve"],
        "last_name": ["Smith", "Jones", "Smith", "Lee", "Kumar", "Patel"],
        "date_of_birth": ["1990-01-01", "1985-05-05", "1990-01-01",
                           "2000-03-03", "1975-07-07", "1995-09-09"],
        "gender": ["F", "m", "F", "Female", "M", "other"],
        "phone_number": [9111111111, 9222222222, 9111111111, None, 9444444444, 9555555555],
        "email": ["a@x.com", "b@x.com", "a@x.com", "c@x.com", None, "e@x.com"],
        "registration_date": ["2020-01-01", "2020-01-01", "2019-01-01",
                               "2021-01-01", "2020-01-01", "2020-01-01"],
        "blood_group": ["A+", "B+", "A+", "O-", "AB+", "A-"],
        "city": ["Kochi", "Kochi", "Kochi", "Kochi", "Kochi", "Kochi"],
    })


@pytest.fixture
def sample_doctors():
    return pd.DataFrame({
        "doctor_id": [1, 2, 3],
        "first_name": ["John", "Mary", "Sam"],
        "last_name": ["Doe", "Rao", "Iyer"],
        "department": ["Cardiology", "Neurology", "Oncology"],
        "specialization": ["Heart", "Brain", "Cancer"],
        "years_experience": [10, 15, 5],
        "phone_number": [8111111111, 8222222222, 8333333333],
        "hire_date": ["2015-01-01", "2010-01-01", "2018-01-01"],
    })


@pytest.fixture
def sample_appointments():
    """Includes one orphan doctor_id (999) and one orphan patient_id (999)."""
    return pd.DataFrame({
        "appointment_id": [1, 2, 3, 4],
        "patient_id": [1, 2, 999, 3],
        "doctor_id": [1, 999, 2, 3],
        "appointment_date": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"],
        "appointment_time": ["09:00", "10:00", "11:00", "12:00"],
        "status": ["Completed", "Cancelled", "Completed", "No-show"],
        "reason_for_visit": ["Checkup", "Checkup", "Checkup", "Checkup"],
    })


@pytest.fixture
def sample_admissions():
    """Includes one row with discharge_date BEFORE admission_date."""
    return pd.DataFrame({
        "admission_id": [1, 2, 3],
        "patient_id": [1, 2, 3],
        "doctor_id": [1, 2, 3],
        "department": ["Cardiology", "Neurology", "Oncology"],
        "admission_date": ["2024-01-10", "2024-02-10", "2024-03-10"],
        "discharge_date": ["2024-01-15", "2024-02-05", None],  # row 2 = bad date, row 3 = still admitted
        "diagnosis": ["Chest pain", "Migraine", "Tumor"],
        "room_type": ["ICU", "General", "Private"],
    })
    