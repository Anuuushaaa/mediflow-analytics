"""
Tests for etl/extract.py — structural validation only (matches Extract's
own scope: does the file exist, are the right columns present).
"""

import pandas as pd
import pytest

from etl.extract import (
    _validate_file_exists,
    _validate_columns,
    _validate_row_count,
    ExtractionError,
    EXPECTED_SCHEMAS,
)


def test_validate_file_exists_missing_file(tmp_path):
    missing = tmp_path / "does_not_exist.csv"
    with pytest.raises(ExtractionError, match="Missing raw file"):
        _validate_file_exists(missing)


def test_validate_file_exists_empty_file(tmp_path):
    empty_file = tmp_path / "empty.csv"
    empty_file.write_text("")
    with pytest.raises(ExtractionError, match="empty"):
        _validate_file_exists(empty_file)


def test_validate_file_exists_valid_file(tmp_path):
    valid_file = tmp_path / "patients.csv"
    valid_file.write_text("patient_id,first_name\n1,Alice\n")
    # Should NOT raise
    _validate_file_exists(valid_file)


def test_validate_columns_missing_column_raises(sample_patients):
    broken = sample_patients.drop(columns=["email"])
    with pytest.raises(ExtractionError, match="missing expected columns"):
        _validate_columns(broken, "patients")


def test_validate_columns_extra_column_does_not_raise(sample_patients, caplog):
    extended = sample_patients.copy()
    extended["extra_field_from_new_system"] = "x"
    # Should NOT raise — extra columns are only a warning
    _validate_columns(extended, "patients")


def test_validate_columns_correct_schema_passes(sample_patients):
    # sample_patients fixture has exactly the right columns — should pass silently
    _validate_columns(sample_patients, "patients")


def test_validate_row_count_empty_dataframe_raises():
    empty_df = pd.DataFrame(columns=["patient_id", "first_name"])
    with pytest.raises(ExtractionError, match="zero data rows"):
        _validate_row_count(empty_df, "patients")


def test_validate_row_count_nonempty_passes(sample_patients):
    # Should NOT raise
    _validate_row_count(sample_patients, "patients")


def test_all_expected_schemas_defined_for_8_datasets():
    """Sanity check: Phase 2/3 defined exactly 8 datasets — schema dict
    should never silently drift from that."""
    expected_datasets = {
        "patients", "doctors", "appointments", "admissions",
        "lab_results", "pharmacy", "billing", "insurance_claims",
    }
    assert set(EXPECTED_SCHEMAS.keys()) == expected_datasets