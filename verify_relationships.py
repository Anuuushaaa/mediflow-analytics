
import pandas as pd

admissions = pd.read_csv("data/raw/admissions.csv")
billing = pd.read_csv("data/raw/billing.csv")
claims = pd.read_csv("data/raw/insurance_claims.csv")

# Check 1: Billing patients match their admissions
linked_bills = billing.dropna(subset=["admission_id"])

billing_check = linked_bills.merge(
    admissions[["admission_id", "patient_id"]],
    on="admission_id",
    how="left",
    suffixes=("_bill", "_admission"),
    indicator=True,
)

billing_errors = billing_check[
    (billing_check["_merge"] != "both")
    | (
        billing_check["patient_id_bill"]
        != billing_check["patient_id_admission"]
    )
]

# Check 2: Insurance patients match their bills
claims_check = claims.merge(
    billing[["bill_id", "patient_id"]],
    on="bill_id",
    how="left",
    suffixes=("_claim", "_bill"),
    indicator=True,
)

insurance_errors = claims_check[
    (claims_check["_merge"] != "both")
    | (
        claims_check["patient_id_claim"]
        != claims_check["patient_id_bill"]
    )
]

print("Admission-linked bills:", len(linked_bills))
print("Billing mismatches:", len(billing_errors))
print("Insurance claims:", len(claims))
print("Insurance mismatches:", len(insurance_errors))

assert len(billing_errors) == 0
assert len(insurance_errors) == 0

print("PASS: All billing and insurance relationships are valid.")
