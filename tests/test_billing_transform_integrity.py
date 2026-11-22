
import pandas as pd

import etl.transform as transform


def test_billing_mismatched_patient_is_quarantined(
    tmp_path, monkeypatch
):
    # Keep test quarantine files separate from real project data.
    monkeypatch.setattr(
        transform, "REJECTED_DIR", tmp_path / "rejected"
    )

    admissions = pd.DataFrame({
        "admission_id": [101, 102],
        "patient_id": [10, 20],
    })

    billing = pd.DataFrame({
        "bill_id": [1, 2, 3],
        "patient_id": [10, 99, 20],
        "admission_id": [101, 101, None],
        "bill_date": ["2026-01-01"] * 3,
        "amount": [1000, 2000, 3000],
    })

    clean = transform.transform_billing(
        billing,
        valid_patient_ids={10, 20, 99},
        admissions=admissions
    )

    # Bill 2 has an existing patient and admission,
    # but the admission belongs to another patient.
    assert set(clean["bill_id"]) == {1, 3}

    rejected = pd.read_csv(
        tmp_path / "rejected" / "billing_rejected.csv"
    )

    assert 2 in rejected["bill_id"].values
    assert (
        rejected.loc[
            rejected["bill_id"] == 2,
            "rejection_reason"
        ].iloc[0]
        == "billing patient_id does not match admission patient_id"
    )
