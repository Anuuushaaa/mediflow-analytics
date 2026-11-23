
import pandas as pd

import etl.transform as transform


def test_insurance_mismatched_patient_is_quarantined(
    tmp_path, monkeypatch
):
    # Isolate test quarantine output
    monkeypatch.setattr(
        transform, "REJECTED_DIR", tmp_path / "rejected"
    )

    billing = pd.DataFrame({
        "bill_id": [101, 102],
        "patient_id": [10, 20],
    })

    claims = pd.DataFrame({
        "claim_id": [1, 2, 3],
        "bill_id": [101, 102, 102],
        "patient_id": [10, 10, 20],
        "claim_date": ["2026-01-01"] * 3,
    })

    clean = transform.transform_insurance_claims(
        claims,
        billing,
        valid_patient_ids={10, 20}
    )

    # Claim 2 belongs to the wrong patient
    assert set(clean["claim_id"]) == {1, 3}

    rejected = pd.read_csv(
        tmp_path / "rejected"
        / "insurance_claims_rejected.csv"
    )

    assert set(rejected["claim_id"]) == {2}

    assert (
        rejected.loc[
            rejected["claim_id"] == 2,
            "rejection_reason"
        ].iloc[0]
        == "insurance patient_id does not match billing patient_id"
    )
