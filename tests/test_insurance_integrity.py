
import random

import pandas as pd

from scripts.generate_data import generate_insurance_claims


def test_insurance_patient_matches_bill(monkeypatch):
    billing = pd.DataFrame({
        "bill_id": [101, 102, 103],
        "patient_id": [10, 20, 30],
    })

    monkeypatch.setattr(
        "scripts.generate_data.N_INSURANCE_CLAIMS", 100
    )

    random.seed(42)

    claims = generate_insurance_claims(billing)

    bill_to_patient = billing.set_index(
        "bill_id"
    )["patient_id"]

    assert len(claims) == 100

    for _, claim in claims.iterrows():
        expected_patient = bill_to_patient.loc[
            claim["bill_id"]
        ]

        assert claim["patient_id"] == expected_patient
