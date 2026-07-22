"""
MediFlow Analytics — Transform Layer (Phase 5)

Cleans, standardizes, and enriches the 8 extracted DataFrames.

Content validation happens HERE (not Extract) — this is where every
data quality issue seeded in Phase 2 gets addressed:
  - Duplicate patient records
  - Inconsistent gender casing
  - Missing email/phone (kept, just flagged — missing contact info
    isn't disqualifying, just incomplete)
  - Negative billing amounts / lab turnaround hours (quarantined)
  - Discharge date before admission date (quarantined)
  - Orphan patient_id / doctor_id / admission_id / bill_id in EVERY
    child table (appointments, admissions, lab_results, pharmacy,
    billing, insurance_claims) — quarantined because Phase 3's schema
    enforces STRICT foreign keys; these rows would be rejected by
    PostgreSQL at Load time otherwise. Deduplicating patients (or
    quarantining bad billing rows) can orphan references in ANY
    downstream table that points at that ID, not just appointments.

Rejected rows are never silently dropped — they're written to
data/processed/rejected/<dataset>_rejected.csv with a reason column,
so a real data-quality team could review and fix the source issue.

Usage:
    from etl.transform import transform_all
    clean_data = transform_all(raw_dataframes)
"""

import logging
from pathlib import Path
from datetime import date

import pandas as pd

logger = logging.getLogger("etl.transform")

REJECTED_DIR = Path("data/processed/rejected")
PROCESSED_DIR = Path("data/processed")


def _quarantine(df: pd.DataFrame, reason: str, dataset_name: str) -> pd.DataFrame:
    """Write rejected rows to a quarantine CSV (append reason column) and
    return them so the caller can log a count. Does not raise."""
    if df.empty:
        return df
    REJECTED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REJECTED_DIR / f"{dataset_name}_rejected.csv"

    rejected = df.copy()
    rejected["rejection_reason"] = reason

    write_header = not out_path.exists()
    rejected.to_csv(out_path, mode="a", header=write_header, index=False)
    logger.warning(f"[{dataset_name}] quarantined {len(df)} row(s): {reason}")
    return df


def _filter_orphan_fk(df: pd.DataFrame, fk_column: str, valid_ids: set, dataset_name: str) -> pd.DataFrame:
    """
    Shared orphan-FK filter used by EVERY table that references patients,
    doctors, or billing. This must run on every child table, not just
    appointments — deduplicating patients (or quarantining bad billing
    rows) can orphan references in ANY table that points at that ID,
    which is exactly what surfaced as a ForeignKeyViolation at Load time
    on 'admissions' during real-world testing of this pipeline.
    """
    orphan_mask = ~df[fk_column].isin(valid_ids)
    if orphan_mask.any():
        _quarantine(df[orphan_mask], f"{fk_column} does not exist in referenced table", dataset_name)
    return df[~orphan_mask]


# ---------------------------------------------------------------------------
# PATIENTS
# ---------------------------------------------------------------------------
def transform_patients(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # 1. Standardize gender casing/values
    gender_map = {
        "m": "M", "male": "M", "M": "M",
        "f": "F", "female": "F", "F": "F",
        "other": "Other", "Other": "Other",
    }
    df["gender"] = df["gender"].astype(str).str.strip().map(
        lambda g: gender_map.get(g, gender_map.get(g.lower(), "Unknown"))
    )

    # 2. Deduplicate on (first_name, last_name, date_of_birth) — same person
    #    registered twice keeps the FIRST (earliest patient_id) occurrence
    before = len(df)
    dup_mask = df.duplicated(subset=["first_name", "last_name", "date_of_birth"], keep="first")
    duplicates = df[dup_mask]
    _quarantine(duplicates, "duplicate patient (same name + DOB as an earlier record)", "patients")
    df = df[~dup_mask]
    logger.info(f"[patients] removed {before - len(df)} duplicate row(s)")

    # 3. Fix phone_number dtype corruption: pandas upgrades this column to
    #    float64 (e.g. 9362950628.0) whenever ANY row is missing, since
    #    integer columns can't hold NaN. Must explicitly convert back to
    #    clean string (or true null), or the ".0" gets written into
    #    PostgreSQL as literal text.
    df["phone_number"] = df["phone_number"].apply(
        lambda x: str(int(x)) if pd.notna(x) else None
    )

    # 4. Missing email/phone — NOT disqualifying, just flagged for visibility
    missing_email = df["email"].isna().sum()

    missing_phone = df["phone_number"].isna().sum()
    logger.info(f"[patients] {missing_email} row(s) missing email, {missing_phone} missing phone (kept, flagged)")

    # 4. Derived columns: age, age_group
    df["date_of_birth"] = pd.to_datetime(df["date_of_birth"])
    today = pd.Timestamp(date.today())
    df["age"] = ((today - df["date_of_birth"]).dt.days // 365).astype(int)

    bins = [0, 17, 35, 55, 75, 200]
    labels = ["0-17", "18-35", "36-55", "56-75", "76+"]
    df["age_group"] = pd.cut(df["age"], bins=bins, labels=labels, right=True)

    return df


# ---------------------------------------------------------------------------
# DOCTORS — clean pass-through (no seeded issues, but standardize dtypes)
# ---------------------------------------------------------------------------
def transform_doctors(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["hire_date"] = pd.to_datetime(df["hire_date"])
    return df


# ---------------------------------------------------------------------------
# APPOINTMENTS
# ---------------------------------------------------------------------------
def transform_appointments(df: pd.DataFrame, valid_doctor_ids: set, valid_patient_ids: set) -> pd.DataFrame:
    df = df.copy()
    df["appointment_date"] = pd.to_datetime(df["appointment_date"])

    # 1. Orphan doctor_id / patient_id — required quarantine since Phase 3
    #    schema has strict FK constraints; these rows would be rejected at Load
    df = _filter_orphan_fk(df, "doctor_id", valid_doctor_ids, "appointments")
    df = _filter_orphan_fk(df, "patient_id", valid_patient_ids, "appointments")

    # 3. Future-dated appointments beyond today — flag/quarantine as a
    #    scheduling-bug indicator
    future_mask = df["appointment_date"] > pd.Timestamp(date.today())
    _quarantine(df[future_mask], "appointment_date is in the future (scheduling bug)", "appointments")
    df = df[~future_mask]

    return df


# ---------------------------------------------------------------------------
# ADMISSIONS
# ---------------------------------------------------------------------------
def transform_admissions(df: pd.DataFrame, valid_patient_ids: set, valid_doctor_ids: set) -> pd.DataFrame:
    df = df.copy()
    df["admission_date"] = pd.to_datetime(df["admission_date"])
    df["discharge_date"] = pd.to_datetime(df["discharge_date"], errors="coerce")

    # 0. Orphan patient_id / doctor_id (can arise after patient dedup in
    #    transform_patients — must be checked in every child table, not
    #    just appointments)
    df = _filter_orphan_fk(df, "patient_id", valid_patient_ids, "admissions")
    df = _filter_orphan_fk(df, "doctor_id", valid_doctor_ids, "admissions")

    # 1. Discharge before admission — quarantine (violates chk_admissions_
    #    discharge_after_admission in schema.sql; would fail at Load)
    bad_dates_mask = df["discharge_date"].notna() & (df["discharge_date"] < df["admission_date"])
    _quarantine(df[bad_dates_mask], "discharge_date is before admission_date", "admissions")
    df = df[~bad_dates_mask]

    # 2. Derived column: length_of_stay (only for discharged patients;
    #    NaN/null for still-admitted patients — correctly reflects "unknown yet")
    df["length_of_stay_days"] = (df["discharge_date"] - df["admission_date"]).dt.days

    return df


# ---------------------------------------------------------------------------
# LAB RESULTS
# ---------------------------------------------------------------------------
def transform_lab_results(df: pd.DataFrame, valid_patient_ids: set, valid_doctor_ids: set) -> pd.DataFrame:
    df = df.copy()
    df["test_date"] = pd.to_datetime(df["test_date"])

    df = _filter_orphan_fk(df, "patient_id", valid_patient_ids, "lab_results")
    df = _filter_orphan_fk(df, "doctor_id", valid_doctor_ids, "lab_results")

    # Negative turnaround hours — physically impossible, quarantine
    negative_mask = df["turnaround_hours"] < 0
    _quarantine(df[negative_mask], "turnaround_hours is negative (impossible)", "lab_results")
    df = df[~negative_mask]

    return df


# ---------------------------------------------------------------------------
# PHARMACY — clean pass-through
# ---------------------------------------------------------------------------
def transform_pharmacy(df: pd.DataFrame, valid_patient_ids: set, valid_doctor_ids: set) -> pd.DataFrame:
    df = df.copy()
    df["prescribed_date"] = pd.to_datetime(df["prescribed_date"])
    df = _filter_orphan_fk(df, "patient_id", valid_patient_ids, "pharmacy")
    df = _filter_orphan_fk(df, "doctor_id", valid_doctor_ids, "pharmacy")
    return df


# ---------------------------------------------------------------------------
# BILLING
# ---------------------------------------------------------------------------
def transform_billing(df: pd.DataFrame, valid_patient_ids: set, valid_admission_ids: set) -> pd.DataFrame:
    df = df.copy()
    df["bill_date"] = pd.to_datetime(df["bill_date"])

    df = _filter_orphan_fk(df, "patient_id", valid_patient_ids, "billing")

    # admission_id is NULLABLE (a bill may not tie to an admission at all),
    # so only quarantine rows where it's set AND doesn't match a real admission
    orphan_admission_mask = df["admission_id"].notna() & ~df["admission_id"].isin(valid_admission_ids)
    if orphan_admission_mask.any():
        _quarantine(df[orphan_admission_mask], "admission_id does not exist in admissions table", "billing")
    df = df[~orphan_admission_mask]

    # Negative billing amount — quarantine (violates chk_billing_amount_nonneg)
    negative_mask = df["amount"] < 0
    _quarantine(df[negative_mask], "billing amount is negative", "billing")
    df = df[~negative_mask]

    # Derived column: revenue_category (used by financial dashboards)
    bins = [-1, 5000, 20000, 75000, float("inf")]
    labels = ["Low", "Medium", "High", "Very High"]
    df["revenue_category"] = pd.cut(df["amount"], bins=bins, labels=labels)

    return df


# ---------------------------------------------------------------------------
# INSURANCE CLAIMS — clean pass-through
# ---------------------------------------------------------------------------
def transform_insurance_claims(df: pd.DataFrame, valid_bill_ids: set, valid_patient_ids: set) -> pd.DataFrame:
    df = df.copy()
    df["claim_date"] = pd.to_datetime(df["claim_date"])
    df = _filter_orphan_fk(df, "bill_id", valid_bill_ids, "insurance_claims")
    df = _filter_orphan_fk(df, "patient_id", valid_patient_ids, "insurance_claims")
    return df


# ---------------------------------------------------------------------------
# ORCHESTRATOR
# ---------------------------------------------------------------------------
def transform_all(raw: dict) -> dict:
    """
    Apply all transformations in dependency order (patients/doctors first,
    since other tables validate against their ID sets).
    """
    logger.info("=" * 70)
    logger.info("Starting transformation of all datasets")
    logger.info("=" * 70)

    # Clear any prior quarantine files so re-runs don't duplicate rejected rows
    if REJECTED_DIR.exists():
        for f in REJECTED_DIR.glob("*_rejected.csv"):
            f.unlink()

    clean = {}
    clean["patients"] = transform_patients(raw["patients"])
    clean["doctors"] = transform_doctors(raw["doctors"])

    valid_patient_ids = set(clean["patients"]["patient_id"])
    valid_doctor_ids = set(clean["doctors"]["doctor_id"])

    clean["appointments"] = transform_appointments(raw["appointments"], valid_doctor_ids, valid_patient_ids)
    clean["admissions"] = transform_admissions(raw["admissions"], valid_patient_ids, valid_doctor_ids)
    clean["lab_results"] = transform_lab_results(raw["lab_results"], valid_patient_ids, valid_doctor_ids)
    clean["pharmacy"] = transform_pharmacy(raw["pharmacy"], valid_patient_ids, valid_doctor_ids)

    valid_admission_ids = set(clean["admissions"]["admission_id"])
    clean["billing"] = transform_billing(raw["billing"], valid_patient_ids, valid_admission_ids)

    valid_bill_ids = set(clean["billing"]["bill_id"])
    clean["insurance_claims"] = transform_insurance_claims(raw["insurance_claims"], valid_bill_ids, valid_patient_ids)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    for name, df in clean.items():
        df.to_csv(PROCESSED_DIR / f"{name}.csv", index=False)

    logger.info("Transformation complete. Clean row counts:")
    for name, df in clean.items():
        logger.info(f"  {name:20s} {len(df):>7,} rows")

    return clean


if __name__ == "__main__":
    from etl.extract import extract_all
    raw = extract_all()
    clean = transform_all(raw)
