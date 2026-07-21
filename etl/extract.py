"""
MediFlow Analytics — Extract Layer (Phase 4)

Reads all 8 raw hospital CSVs and validates their STRUCTURE (not content):
  - File exists and is readable
  - Expected columns are present (no missing/extra/misnamed columns)
  - File is not empty

Content validation (bad ages, invalid dates, duplicates, etc.) is
deliberately OUT OF SCOPE here — that's the Transform layer's job
(Phase 5). Extract's only responsibility is: "can I trust the shape
of this data enough to hand it downstream?"

Usage:
    from etl.extract import extract_all
    dataframes = extract_all()
"""

import logging
import sys
from pathlib import Path

import pandas as pd
import yaml

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "etl_pipeline.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("etl.extract")


# ---------------------------------------------------------------------------
# Expected schema definitions — the contract each raw file must satisfy.
# If a source system changes its export format, this is what catches it.
# ---------------------------------------------------------------------------
EXPECTED_SCHEMAS = {
    "patients": [
        "patient_id", "first_name", "last_name", "date_of_birth", "gender",
        "phone_number", "email", "registration_date", "blood_group", "city",
    ],
    "doctors": [
        "doctor_id", "first_name", "last_name", "department", "specialization",
        "years_experience", "phone_number", "hire_date",
    ],
    "appointments": [
        "appointment_id", "patient_id", "doctor_id", "appointment_date",
        "appointment_time", "status", "reason_for_visit",
    ],
    "admissions": [
        "admission_id", "patient_id", "doctor_id", "department",
        "admission_date", "discharge_date", "diagnosis", "room_type",
    ],
    "lab_results": [
        "lab_id", "patient_id", "doctor_id", "test_name", "test_date",
        "result_status", "turnaround_hours",
    ],
    "pharmacy": [
        "prescription_id", "patient_id", "doctor_id", "medication_name",
        "quantity", "unit_cost", "prescribed_date",
    ],
    "billing": [
        "bill_id", "patient_id", "admission_id", "bill_date", "amount",
        "payment_status", "payment_method",
    ],
    "insurance_claims": [
        "claim_id", "bill_id", "patient_id", "insurance_provider",
        "claim_amount", "claim_status", "claim_date",
    ],
}


class ExtractionError(Exception):
    """Raised when a raw file fails structural validation."""
    pass


def load_config(config_path: str = "config/config.yaml") -> dict:
    """Load non-secret configuration (raw data directory, etc.)."""
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def _validate_file_exists(filepath: Path) -> None:
    if not filepath.exists():
        raise ExtractionError(f"Missing raw file: {filepath}")
    if filepath.stat().st_size == 0:
        raise ExtractionError(f"Raw file is empty: {filepath}")


def _validate_columns(df: pd.DataFrame, dataset_name: str) -> None:
    expected = set(EXPECTED_SCHEMAS[dataset_name])
    actual = set(df.columns)

    missing = expected - actual
    extra = actual - expected

    if missing:
        raise ExtractionError(
            f"[{dataset_name}] missing expected columns: {sorted(missing)}"
        )
    if extra:
        # Extra columns are a WARNING, not a hard failure — a source system
        # adding a new column shouldn't break the whole pipeline, but we
        # need visibility into it so nobody is surprised later.
        logger.warning(f"[{dataset_name}] unexpected extra columns found: {sorted(extra)}")


def _validate_row_count(df: pd.DataFrame, dataset_name: str) -> None:
    if len(df) == 0:
        raise ExtractionError(f"[{dataset_name}] file parsed but contains zero data rows")


def extract_dataset(dataset_name: str, raw_dir: str) -> pd.DataFrame:
    """
    Extract and structurally validate a single dataset.

    Raises ExtractionError on any structural problem so the pipeline
    fails fast and loud, rather than passing malformed data downstream.
    """
    filepath = Path(raw_dir) / f"{dataset_name}.csv"
    logger.info(f"Extracting {dataset_name} from {filepath}")

    _validate_file_exists(filepath)

    try:
        df = pd.read_csv(filepath)
    except Exception as e:
        raise ExtractionError(f"[{dataset_name}] failed to parse as CSV: {e}") from e

    _validate_columns(df, dataset_name)
    _validate_row_count(df, dataset_name)

    logger.info(f"  -> {dataset_name}: {len(df):,} rows, {len(df.columns)} columns — OK")
    return df


def extract_all(config_path: str = "config/config.yaml") -> dict[str, pd.DataFrame]:
    """
    Extract all 8 hospital datasets. Returns a dict of {name: DataFrame}.

    If ANY dataset fails structural validation, the whole extraction
    aborts — we never want Transform/Load operating on a partial or
    inconsistent set of source tables.
    """
    config = load_config(config_path)
    raw_dir = config["paths"]["raw_data_dir"]

    logger.info("=" * 70)
    logger.info("Starting extraction of all datasets")
    logger.info("=" * 70)

    dataframes = {}
    errors = []

    for dataset_name in EXPECTED_SCHEMAS:
        try:
            dataframes[dataset_name] = extract_dataset(dataset_name, raw_dir)
        except ExtractionError as e:
            logger.error(str(e))
            errors.append(str(e))

    if errors:
        logger.error(f"Extraction FAILED — {len(errors)} dataset(s) had structural errors")
        raise ExtractionError(
            f"Extraction aborted due to {len(errors)} error(s):\n" + "\n".join(errors)
        )

    logger.info(f"Extraction complete — {len(dataframes)}/8 datasets loaded successfully")
    return dataframes


if __name__ == "__main__":
    data = extract_all()
    print("\nSummary:")
    for name, df in data.items():
        print(f"  {name:20s} {len(df):>7,} rows  {len(df.columns):>2} columns")