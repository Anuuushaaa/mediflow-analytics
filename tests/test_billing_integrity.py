
import random

import pandas as pd

from scripts.generate_data import generate_billing


def test_billing_patient_matches_admission(monkeypatch):
    # Small, controlled dataset
    admissions = pd.DataFrame({
        "admission_id": [101, 102, 103],
        "patient_id": [10, 20, 30],
    })

    patient_ids = [10, 20, 30, 40]

    # Generate a manageable number of bills
    monkeypatch.setattr(
        "scripts.generate_data.N_BILLING", 100
    )

    random.seed(42)

    billing = generate_billing(patient_ids, admissions)

    # Check every bill linked to an admission
    linked_bills = billing.dropna(subset=["admission_id"])

    admission_to_patient = admissions.set_index(
        "admission_id"
    )["patient_id"]

    assert not linked_bills.empty

    for _, bill in linked_bills.iterrows():
        expected_patient = admission_to_patient.loc[
            bill["admission_id"]
        ]

        assert bill["patient_id"] == expected_patient
