"""
Tests for etl/transform.py — the business-rule / content-validation layer.
Each test targets ONE specific rule, mirroring the real seeded data quality
issues from Phase 2 and the two real bugs we found and fixed during
development (phone_number float corruption, orphan-FK cascade across
all child tables, not just appointments).
"""

import pandas as pd

from etl.transform import (
    transform_patients,
    transform_appointments,
    transform_admissions,
    _filter_orphan_fk,
)


class TestTransformPatients:

    def test_removes_duplicate_patients(self, sample_patients):
        result = transform_patients(sample_patients)
        # patient_id 3 is a duplicate of patient_id 1 (same name + DOB) -> removed
        assert len(result) == 5
        assert 3 not in result["patient_id"].values

    def test_standardizes_gender_casing(self, sample_patients):
        result = transform_patients(sample_patients)
        # "m", "Female", "other" should all normalize to M / F / Other
        genders = set(result["gender"].unique())
        assert genders <= {"M", "F", "Other"}
        assert "m" not in genders
        assert "Female" not in genders

    def test_phone_number_has_no_float_suffix(self, sample_patients):
        """Regression test for the real bug found in this project: pandas
        upcasts phone_number to float64 (producing '.0' suffixes) whenever
        ANY row has a missing value. This must never resurface."""
        result = transform_patients(sample_patients)
        phone_values = result["phone_number"].dropna().astype(str)
        assert not phone_values.str.contains(r"\.0$").any(), (
            "phone_number contains a float '.0' suffix — the dtype "
            "corruption bug has regressed"
        )

    def test_missing_phone_number_becomes_true_null_not_string_none(self, sample_patients):
        result = transform_patients(sample_patients)
        missing_row = result[result["patient_id"] == 4]
        assert missing_row["phone_number"].isna().all()

    def test_age_is_computed_and_nonnegative(self, sample_patients):
        result = transform_patients(sample_patients)
        assert "age" in result.columns
        assert (result["age"] >= 0).all()

    def test_age_group_bucketing(self, sample_patients):
        result = transform_patients(sample_patients)
        assert "age_group" in result.columns
        assert result["age_group"].notna().all()


class TestOrphanForeignKeyFiltering:
    """Regression tests for the real cascading-orphan-FK bug: originally
    only appointments checked for orphan patient_id/doctor_id; the fix
    applies _filter_orphan_fk to EVERY child table. These tests confirm
    the shared helper itself works correctly in isolation."""

    def test_filters_out_orphan_doctor_id(self, sample_appointments):
        valid_doctor_ids = {1, 2, 3}
        result = _filter_orphan_fk(sample_appointments, "doctor_id", valid_doctor_ids, "test")
        assert 999 not in result["doctor_id"].values
        assert len(result) == 3  # one row had doctor_id=999

    def test_filters_out_orphan_patient_id(self, sample_appointments):
        valid_patient_ids = {1, 2, 3}
        result = _filter_orphan_fk(sample_appointments, "patient_id", valid_patient_ids, "test")
        assert 999 not in result["patient_id"].values

    def test_keeps_all_rows_when_no_orphans_exist(self, sample_admissions):
        valid_patient_ids = {1, 2, 3}
        result = _filter_orphan_fk(sample_admissions, "patient_id", valid_patient_ids, "test")
        assert len(result) == len(sample_admissions)

    def test_appointments_transform_removes_both_orphan_types(
        self, sample_appointments
    ):
        valid_doctor_ids = {1, 2, 3}
        valid_patient_ids = {1, 2, 3}
        result = transform_appointments(sample_appointments, valid_doctor_ids, valid_patient_ids)
        # Only appointment_id 1 and 4 have BOTH a valid doctor_id and patient_id
        assert set(result["appointment_id"]) == {1, 4}


class TestTransformAdmissions:

    def test_quarantines_discharge_before_admission(self, sample_admissions):
        valid_patient_ids = {1, 2, 3}
        valid_doctor_ids = {1, 2, 3}
        result = transform_admissions(sample_admissions, valid_patient_ids, valid_doctor_ids)
        # admission_id=2 has discharge_date BEFORE admission_date -> must be removed
        assert 2 not in result["admission_id"].values

    def test_null_discharge_date_is_preserved_not_rejected(self, sample_admissions):
        """A still-admitted patient (null discharge_date) is valid data,
        not an error — must NOT be quarantined."""
        valid_patient_ids = {1, 2, 3}
        valid_doctor_ids = {1, 2, 3}
        result = transform_admissions(sample_admissions, valid_patient_ids, valid_doctor_ids)
        assert 3 in result["admission_id"].values

    def test_length_of_stay_is_null_for_still_admitted(self, sample_admissions):
        valid_patient_ids = {1, 2, 3}
        valid_doctor_ids = {1, 2, 3}
        result = transform_admissions(sample_admissions, valid_patient_ids, valid_doctor_ids)
        row = result[result["admission_id"] == 3]
        assert row["length_of_stay_days"].isna().all()

    def test_length_of_stay_computed_correctly_for_discharged_patient(self, sample_admissions):
        valid_patient_ids = {1, 2, 3}
        valid_doctor_ids = {1, 2, 3}
        result = transform_admissions(sample_admissions, valid_patient_ids, valid_doctor_ids)
        row = result[result["admission_id"] == 1]
        # admitted 2024-01-10, discharged 2024-01-15 -> 5 days
        assert row["length_of_stay_days"].iloc[0] == 5