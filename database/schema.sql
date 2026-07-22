-- =============================================================================
-- MediFlow Analytics — Database Schema (Phase 3)
-- PostgreSQL DDL for 8 normalized tables representing hospital source systems.
--
-- Design principles:
--   - 3NF normalization: no derived/redundant columns (e.g. age is computed,
--     not stored; length_of_stay is computed, not stored)
--   - Strict referential integrity: FK constraints reject orphan references
--     (bad rows must be cleaned in the Transform layer before Load, per
--     Phase 2/3 decision — the database is the last line of defense, not
--     the primary filter)
--   - ON DELETE RESTRICT on clinical/financial FKs: hospital records are
--     never silently cascade-deleted, for audit/compliance reasons
--   - CHECK constraints enforce business rules at the data layer
-- =============================================================================

DROP TABLE IF EXISTS insurance_claims CASCADE;
DROP TABLE IF EXISTS billing CASCADE;
DROP TABLE IF EXISTS pharmacy CASCADE;
DROP TABLE IF EXISTS lab_results CASCADE;
DROP TABLE IF EXISTS admissions CASCADE;
DROP TABLE IF EXISTS appointments CASCADE;
DROP TABLE IF EXISTS doctors CASCADE;
DROP TABLE IF EXISTS patients CASCADE;


-- =============================================================================
-- PATIENTS — root entity, referenced by nearly every other table
-- =============================================================================
CREATE TABLE patients (
    patient_id          INTEGER PRIMARY KEY,
    first_name          VARCHAR(50)  NOT NULL,
    last_name           VARCHAR(50)  NOT NULL,
    date_of_birth       DATE         NOT NULL,
    gender              VARCHAR(10)  NOT NULL,
    phone_number        VARCHAR(20),
    email               VARCHAR(100),
    registration_date   DATE         NOT NULL,
    blood_group         VARCHAR(3),
    city                VARCHAR(50),

    CONSTRAINT chk_patients_dob_past
        CHECK (date_of_birth <= CURRENT_DATE),
    CONSTRAINT chk_patients_registration_after_dob
        CHECK (registration_date >= date_of_birth)
);

CREATE INDEX idx_patients_city ON patients(city);
CREATE INDEX idx_patients_registration_date ON patients(registration_date);


-- =============================================================================
-- DOCTORS
-- =============================================================================
CREATE TABLE doctors (
    doctor_id           INTEGER PRIMARY KEY,
    first_name          VARCHAR(50)  NOT NULL,
    last_name           VARCHAR(50)  NOT NULL,
    department          VARCHAR(50)  NOT NULL,
    specialization       VARCHAR(50),
    years_experience    INTEGER      NOT NULL,
    phone_number        VARCHAR(20),
    hire_date           DATE         NOT NULL,

    CONSTRAINT chk_doctors_experience_nonneg
        CHECK (years_experience >= 0)
);

CREATE INDEX idx_doctors_department ON doctors(department);


-- =============================================================================
-- APPOINTMENTS
-- =============================================================================
CREATE TABLE appointments (
    appointment_id      INTEGER PRIMARY KEY,
    patient_id          INTEGER      NOT NULL REFERENCES patients(patient_id) ON DELETE RESTRICT,
    doctor_id           INTEGER      NOT NULL REFERENCES doctors(doctor_id)   ON DELETE RESTRICT,
    appointment_date    DATE         NOT NULL,
    appointment_time    TIME         NOT NULL,
    status              VARCHAR(20)  NOT NULL,
    reason_for_visit    VARCHAR(100),

    CONSTRAINT chk_appointments_status
        CHECK (status IN ('Scheduled', 'Completed', 'Cancelled', 'No-show'))
);

CREATE INDEX idx_appointments_patient ON appointments(patient_id);
CREATE INDEX idx_appointments_doctor ON appointments(doctor_id);
CREATE INDEX idx_appointments_date ON appointments(appointment_date);


-- =============================================================================
-- ADMISSIONS
-- =============================================================================
CREATE TABLE admissions (
    admission_id        INTEGER PRIMARY KEY,
    patient_id          INTEGER      NOT NULL REFERENCES patients(patient_id) ON DELETE RESTRICT,
    doctor_id           INTEGER      NOT NULL REFERENCES doctors(doctor_id)   ON DELETE RESTRICT,
    department           VARCHAR(50)  NOT NULL,
    admission_date      DATE         NOT NULL,
    discharge_date       DATE,
    diagnosis             VARCHAR(100) NOT NULL,
    room_type              VARCHAR(20)  NOT NULL,

    CONSTRAINT chk_admissions_discharge_after_admission
        CHECK (discharge_date IS NULL OR discharge_date >= admission_date),
    CONSTRAINT chk_admissions_room_type
        CHECK (room_type IN ('General', 'Private', 'ICU'))
);

CREATE INDEX idx_admissions_patient ON admissions(patient_id);
CREATE INDEX idx_admissions_doctor ON admissions(doctor_id);
CREATE INDEX idx_admissions_department ON admissions(department);


-- =============================================================================
-- LAB RESULTS
-- =============================================================================
CREATE TABLE lab_results (
    lab_id               INTEGER PRIMARY KEY,
    patient_id           INTEGER      NOT NULL REFERENCES patients(patient_id) ON DELETE RESTRICT,
    doctor_id            INTEGER      NOT NULL REFERENCES doctors(doctor_id)   ON DELETE RESTRICT,
    test_name             VARCHAR(50)  NOT NULL,
    test_date             DATE         NOT NULL,
    result_status         VARCHAR(20)  NOT NULL,
    turnaround_hours      NUMERIC(6,2) NOT NULL,

    CONSTRAINT chk_lab_result_status
        CHECK (result_status IN ('Normal', 'Abnormal', 'Pending')),
    CONSTRAINT chk_lab_turnaround_nonneg
        CHECK (turnaround_hours >= 0)
);

CREATE INDEX idx_lab_results_patient ON lab_results(patient_id);
CREATE INDEX idx_lab_results_test_name ON lab_results(test_name);


-- =============================================================================
-- PHARMACY
-- =============================================================================
CREATE TABLE pharmacy (
    prescription_id       INTEGER PRIMARY KEY,
    patient_id            INTEGER      NOT NULL REFERENCES patients(patient_id) ON DELETE RESTRICT,
    doctor_id             INTEGER      NOT NULL REFERENCES doctors(doctor_id)   ON DELETE RESTRICT,
    medication_name        VARCHAR(100) NOT NULL,
    quantity                INTEGER      NOT NULL,
    unit_cost                NUMERIC(10,2) NOT NULL,
    prescribed_date          DATE         NOT NULL,

    CONSTRAINT chk_pharmacy_quantity_positive
        CHECK (quantity > 0),
    CONSTRAINT chk_pharmacy_unit_cost_nonneg
        CHECK (unit_cost >= 0)
);

CREATE INDEX idx_pharmacy_patient ON pharmacy(patient_id);
CREATE INDEX idx_pharmacy_medication ON pharmacy(medication_name);


-- =============================================================================
-- BILLING
-- =============================================================================
CREATE TABLE billing (
    bill_id                INTEGER PRIMARY KEY,
    patient_id             INTEGER      NOT NULL REFERENCES patients(patient_id)     ON DELETE RESTRICT,
    admission_id           INTEGER      REFERENCES admissions(admission_id) ON DELETE RESTRICT,
    bill_date               DATE         NOT NULL,
    amount                   NUMERIC(12,2) NOT NULL,
    payment_status           VARCHAR(20)  NOT NULL,
    payment_method            VARCHAR(20)  NOT NULL,

    CONSTRAINT chk_billing_amount_nonneg
        CHECK (amount >= 0),
    CONSTRAINT chk_billing_payment_status
        CHECK (payment_status IN ('Paid', 'Pending', 'Overdue')),
    CONSTRAINT chk_billing_payment_method
        CHECK (payment_method IN ('Insurance', 'Self-pay', 'Cash'))
);

CREATE INDEX idx_billing_patient ON billing(patient_id);
CREATE INDEX idx_billing_status ON billing(payment_status);


-- =============================================================================
-- INSURANCE CLAIMS
-- =============================================================================
CREATE TABLE insurance_claims (
    claim_id                 INTEGER PRIMARY KEY,
    bill_id                  INTEGER      NOT NULL REFERENCES billing(bill_id)   ON DELETE RESTRICT,
    patient_id                INTEGER      NOT NULL REFERENCES patients(patient_id) ON DELETE RESTRICT,
    insurance_provider          VARCHAR(50)  NOT NULL,
    claim_amount                 NUMERIC(12,2) NOT NULL,
    claim_status                  VARCHAR(20)  NOT NULL,
    claim_date                     DATE         NOT NULL,

    CONSTRAINT chk_claims_amount_nonneg
        CHECK (claim_amount >= 0),
    CONSTRAINT chk_claims_status
        CHECK (claim_status IN ('Approved', 'Rejected', 'Pending'))
);

CREATE INDEX idx_claims_bill ON insurance_claims(bill_id);
CREATE INDEX idx_claims_provider ON insurance_claims(insurance_provider);