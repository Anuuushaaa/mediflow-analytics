"""
MediFlow Analytics — Synthetic Data Generator (Phase 2)

Generates 8 CSVs simulating independent hospital source systems:
patients, doctors, appointments, admissions, lab_results, pharmacy,
billing, insurance_claims.

Intentionally seeds realistic data quality issues (nulls, duplicates,
inconsistent casing, bad dates, orphan foreign keys) so the Transform
layer (Phase 5) has real problems to solve — not a hypothetical.

Run:
    python scripts/generate_data.py
Output:
    data/raw/*.csv
"""

import random
import numpy as np
import pandas as pd
from datetime import date, timedelta

SEED = 42
random.seed(SEED)
np.random.seed(SEED)

N_PATIENTS = 5000
N_DOCTORS = 150
N_APPOINTMENTS = 15000
N_ADMISSIONS = 3000
N_LAB_RESULTS = 8000
N_PHARMACY = 10000
N_BILLING = 6000
N_INSURANCE_CLAIMS = 3000

OUT_DIR = "data/raw"

FIRST_NAMES = ["James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda",
               "William", "Elizabeth", "David", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
               "Thomas", "Sarah", "Charles", "Karen", "Anil", "Priya", "Ravi", "Sunita", "Arjun",
               "Divya", "Vikram", "Neha", "Rahul", "Pooja", "Amit", "Kavya", "Sanjay", "Meera"]
LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
              "Rodriguez", "Martinez", "Nair", "Menon", "Iyer", "Reddy", "Rao", "Kumar", "Sharma",
              "Patel", "Gupta", "Singh", "Verma", "Pillai", "Krishnan", "Das", "Joseph"]

CITIES = ["Kochi", "Ernakulam", "Kottayam", "Thrissur", "Aluva", "Muvattupuzha",
          "Perumbavoor", "Angamaly", "Kalamassery", "Tripunithura"]

DEPARTMENTS = ["Cardiology", "Neurology", "Orthopedics", "Pediatrics", "General Medicine",
               "Oncology", "Dermatology", "Gastroenterology", "Nephrology", "Pulmonology",
               "Emergency", "ICU"]

DIAGNOSES = ["Hypertension", "Type 2 Diabetes", "Pneumonia", "Fracture - Femur",
             "Acute Appendicitis", "Myocardial Infarction", "Asthma Exacerbation",
             "Chronic Kidney Disease", "Gastroenteritis", "Migraine", "Covid-19",
             "Urinary Tract Infection", "Stroke", "Bronchitis"]

TEST_NAMES = ["CBC", "Lipid Panel", "Liver Function Test", "X-Ray Chest", "MRI Brain",
              "CT Scan Abdomen", "Blood Glucose", "Thyroid Panel", "Urinalysis", "ECG"]

MEDICATIONS = ["Paracetamol", "Amoxicillin", "Metformin", "Atorvastatin", "Amlodipine",
               "Omeprazole", "Azithromycin", "Ibuprofen", "Losartan", "Insulin Glargine"]

INSURANCE_PROVIDERS = ["StarHealth", "MediCare Plus", "HDFC Ergo", "ICICI Lombard",
                        "National Insurance", "Bajaj Allianz", "United India"]


def random_date(start: date, end: date) -> date:
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, delta))


def make_name():
    return random.choice(FIRST_NAMES), random.choice(LAST_NAMES)


# ---------------------------------------------------------------------------
# PATIENTS
# ---------------------------------------------------------------------------
def generate_patients():
    rows = []
    for i in range(1, N_PATIENTS + 1):
        fn, ln = make_name()
        dob = random_date(date(1935, 1, 1), date(2023, 12, 31))
        gender = random.choice(["M", "F", "Other"])
        # registration_date must be on/after date_of_birth (a patient cannot
        # register before they were born) AND within the valid system window.
        # This directly satisfies chk_patients_registration_after_dob from
        # Phase 3's schema.sql.
        reg_window_start = max(dob, date(2018, 1, 1))
        reg_window_end = date(2026, 7, 1)
        if reg_window_start > reg_window_end:
            reg_window_start = reg_window_end
        registration_date = random_date(reg_window_start, reg_window_end)
        rows.append({
            "patient_id": i,
            "first_name": fn,
            "last_name": ln,
            "date_of_birth": dob,
            "gender": gender,
            "phone_number": f"9{random.randint(100000000, 999999999)}",
            "email": f"{fn.lower()}.{ln.lower()}{i}@example.com",
            "registration_date": registration_date,
            "blood_group": random.choice(["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"]),
            "city": random.choice(CITIES),
        })
    df = pd.DataFrame(rows)

    # --- Seed data quality issues ---
    # 1. Missing email (5%)
    mask = df.sample(frac=0.05, random_state=1).index
    df.loc[mask, "email"] = None

    # 2. Missing phone number (3%)
    mask = df.sample(frac=0.03, random_state=2).index
    df.loc[mask, "phone_number"] = None

    # 3. Inconsistent gender casing (mimics different staff entering data)
    mask = df.sample(frac=0.08, random_state=3).index
    df.loc[mask, "gender"] = df.loc[mask, "gender"].map(
        {"M": "m", "F": "Female", "Other": "other"}
    )

    # 4. Duplicate patient records (~1.5% of rows duplicated, new IDs, simulating
    #    the same person registered twice at the front desk)
    dup_sample = df.sample(frac=0.015, random_state=4).copy()
    dup_sample["patient_id"] = range(N_PATIENTS + 1, N_PATIENTS + 1 + len(dup_sample))
    df = pd.concat([df, dup_sample], ignore_index=True)

    return df


# ---------------------------------------------------------------------------
# DOCTORS
# ---------------------------------------------------------------------------
def generate_doctors():
    rows = []
    for i in range(1, N_DOCTORS + 1):
        fn, ln = make_name()
        rows.append({
            "doctor_id": i,
            "first_name": fn,
            "last_name": ln,
            "department": random.choice(DEPARTMENTS),
            "specialization": random.choice(DIAGNOSES)[:20],
            "years_experience": random.randint(1, 35),
            "phone_number": f"8{random.randint(100000000, 999999999)}",
            "hire_date": random_date(date(1995, 1, 1), date(2025, 1, 1)),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# APPOINTMENTS
# ---------------------------------------------------------------------------
def generate_appointments(patient_ids, doctor_ids):
    rows = []
    statuses = ["Completed", "Completed", "Completed", "Scheduled", "Cancelled", "No-show"]
    for i in range(1, N_APPOINTMENTS + 1):
        rows.append({
            "appointment_id": i,
            "patient_id": random.choice(patient_ids),
            "doctor_id": random.choice(doctor_ids),
            "appointment_date": random_date(date(2023, 1, 1), date(2026, 7, 20)),
            "appointment_time": f"{random.randint(8,17):02d}:{random.choice(['00','15','30','45'])}",
            "status": random.choice(statuses),
            "reason_for_visit": random.choice(DIAGNOSES),
        })
    df = pd.DataFrame(rows)

    # --- Seed issues ---
    # 1. Orphan doctor_id (doctor no longer exists in doctors table) — 1%
    mask = df.sample(frac=0.01, random_state=5).index
    df.loc[mask, "doctor_id"] = df.loc[mask, "doctor_id"] + 9000  # doesn't exist in doctors.csv

    # 2. Future appointment dates beyond "today" (scheduling bug) — 0.5%
    mask = df.sample(frac=0.005, random_state=6).index
    df.loc[mask, "appointment_date"] = [
        random_date(date(2026, 8, 1), date(2027, 12, 31)) for _ in range(len(mask))
    ]

    return df


# ---------------------------------------------------------------------------
# ADMISSIONS
# ---------------------------------------------------------------------------
def generate_admissions(patient_ids, doctor_ids):
    rows = []
    for i in range(1, N_ADMISSIONS + 1):
        adm_date = random_date(date(2023, 1, 1), date(2026, 7, 15))
        # Most admissions have a discharge date after admission; ~8% still admitted (null)
        if random.random() < 0.08:
            disch_date = None
        else:
            disch_date = adm_date + timedelta(days=random.randint(0, 21))
        rows.append({
            "admission_id": i,
            "patient_id": random.choice(patient_ids),
            "doctor_id": random.choice(doctor_ids),
            "department": random.choice(DEPARTMENTS),
            "admission_date": adm_date,
            "discharge_date": disch_date,
            "diagnosis": random.choice(DIAGNOSES),
            "room_type": random.choice(["General", "Private", "ICU"]),
        })
    df = pd.DataFrame(rows)

    # --- Seed issue: discharge_date BEFORE admission_date (data entry error) — 1.5%
    valid_mask = df["discharge_date"].notna()
    error_candidates = df[valid_mask].sample(frac=0.015, random_state=7).index
    df.loc[error_candidates, "discharge_date"] = (
        pd.to_datetime(df.loc[error_candidates, "admission_date"]) - pd.to_timedelta(
            np.random.randint(1, 5, size=len(error_candidates)), unit="D"
        )
    ).dt.date

    return df


# ---------------------------------------------------------------------------
# LAB RESULTS
# ---------------------------------------------------------------------------
def generate_lab_results(patient_ids, doctor_ids):
    rows = []
    for i in range(1, N_LAB_RESULTS + 1):
        rows.append({
            "lab_id": i,
            "patient_id": random.choice(patient_ids),
            "doctor_id": random.choice(doctor_ids),
            "test_name": random.choice(TEST_NAMES),
            "test_date": random_date(date(2023, 1, 1), date(2026, 7, 20)),
            "result_status": random.choice(["Normal", "Normal", "Abnormal", "Pending"]),
            "turnaround_hours": round(np.random.gamma(shape=2.0, scale=6.0), 1),
        })
    df = pd.DataFrame(rows)

    # Seed issue: a few negative/nonsensical turnaround hours (sensor/logging glitch) — 0.5%
    mask = df.sample(frac=0.005, random_state=8).index
    df.loc[mask, "turnaround_hours"] = -abs(df.loc[mask, "turnaround_hours"])

    return df


# ---------------------------------------------------------------------------
# PHARMACY
# ---------------------------------------------------------------------------
def generate_pharmacy(patient_ids, doctor_ids):
    rows = []
    for i in range(1, N_PHARMACY + 1):
        rows.append({
            "prescription_id": i,
            "patient_id": random.choice(patient_ids),
            "doctor_id": random.choice(doctor_ids),
            "medication_name": random.choice(MEDICATIONS),
            "quantity": random.randint(1, 60),
            "unit_cost": round(random.uniform(2, 250), 2),
            "prescribed_date": random_date(date(2023, 1, 1), date(2026, 7, 20)),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# BILLING
# ---------------------------------------------------------------------------
def generate_billing(patient_ids, admission_ids):
    rows = []
    for i in range(1, N_BILLING + 1):
        rows.append({
            "bill_id": i,
            "patient_id": random.choice(patient_ids),
            "admission_id": random.choice(admission_ids + [None] * 5),  # some bills aren't tied to admission
            "bill_date": random_date(date(2023, 1, 1), date(2026, 7, 20)),
            "amount": round(random.uniform(500, 250000), 2),
            "payment_status": random.choice(["Paid", "Pending", "Overdue"]),
            "payment_method": random.choice(["Insurance", "Self-pay", "Cash"]),
        })
    df = pd.DataFrame(rows)

    # Seed issue: negative billing amounts (data entry/refund logging error) — 1%
    mask = df.sample(frac=0.01, random_state=9).index
    df.loc[mask, "amount"] = -abs(df.loc[mask, "amount"])

    return df


# ---------------------------------------------------------------------------
# INSURANCE CLAIMS
# ---------------------------------------------------------------------------
def generate_insurance_claims(bill_ids, patient_ids):
    rows = []
    for i in range(1, N_INSURANCE_CLAIMS + 1):
        rows.append({
            "claim_id": i,
            "bill_id": random.choice(bill_ids),
            "patient_id": random.choice(patient_ids),
            "insurance_provider": random.choice(INSURANCE_PROVIDERS),
            "claim_amount": round(random.uniform(500, 200000), 2),
            "claim_status": random.choice(["Approved", "Rejected", "Pending"]),
            "claim_date": random_date(date(2023, 1, 1), date(2026, 7, 20)),
        })
    return pd.DataFrame(rows)


def main():
    print("Generating patients...")
    patients = generate_patients()

    print("Generating doctors...")
    doctors = generate_doctors()

    patient_ids = patients["patient_id"].tolist()
    doctor_ids = doctors["doctor_id"].tolist()

    print("Generating appointments...")
    appointments = generate_appointments(patient_ids, doctor_ids)

    print("Generating admissions...")
    admissions = generate_admissions(patient_ids, doctor_ids)
    admission_ids = admissions["admission_id"].tolist()

    print("Generating lab_results...")
    lab_results = generate_lab_results(patient_ids, doctor_ids)

    print("Generating pharmacy...")
    pharmacy = generate_pharmacy(patient_ids, doctor_ids)

    print("Generating billing...")
    billing = generate_billing(patient_ids, admission_ids)
    bill_ids = billing["bill_id"].tolist()

    print("Generating insurance_claims...")
    insurance_claims = generate_insurance_claims(bill_ids, patient_ids)

    datasets = {
        "patients": patients,
        "doctors": doctors,
        "appointments": appointments,
        "admissions": admissions,
        "lab_results": lab_results,
        "pharmacy": pharmacy,
        "billing": billing,
        "insurance_claims": insurance_claims,
    }

    import os
    os.makedirs(OUT_DIR, exist_ok=True)
    for name, df in datasets.items():
        path = f"{OUT_DIR}/{name}.csv"
        df.to_csv(path, index=False)
        print(f"  wrote {path}  ({len(df):,} rows)")

    print("\nDone. All 8 raw CSVs generated in", OUT_DIR)


if __name__ == "__main__":
    main()