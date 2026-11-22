
import pandas as pd
from pathlib import Path

DATA_DIR = Path("data/processed")

patients = pd.read_csv(DATA_DIR / "patients.csv")
admissions = pd.read_csv(DATA_DIR / "admissions.csv")
billing = pd.read_csv(DATA_DIR / "billing.csv")
claims = pd.read_csv(DATA_DIR / "insurance_claims.csv")

# Check 1: Every billing patient must exist
invalid_patients = ~billing["patient_id"].isin(
    patients["patient_id"]
)
assert not invalid_patients.any(), "Billing has invalid patient IDs"

# Check 2: Admission-linked bills must match their patients
linked_bills = billing[billing["admission_id"].notna()].copy()

admission_patients = admissions.set_index(
    "admission_id"
)["patient_id"]

expected_patients = linked_bills["admission_id"].map(
    admission_patients
)

assert expected_patients.notna().all(), (
    "Billing references nonexistent admissions"
)

assert (
    linked_bills["patient_id"].to_numpy()
    == expected_patients.to_numpy()
).all(), "Billing patient/admission mismatch"

# Check 3: Every insurance claim must match its bill's patient
bill_patients = billing.set_index("bill_id")["patient_id"]

expected_claim_patients = claims["bill_id"].map(
    bill_patients
)

assert expected_claim_patients.notna().all(), (
    "Insurance claims reference nonexistent bills"
)

assert (
    claims["patient_id"].to_numpy()
    == expected_claim_patients.to_numpy()
).all(), "Insurance claim patient/bill mismatch"

print("All processed billing and insurance relationships are valid!")
print(f"Verified {len(billing):,} bills")
print(f"Verified {len(claims):,} insurance claims")
