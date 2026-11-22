-- =============================================================================
-- MediFlow Analytics — SQL Analytics Queries (Phase 7)
-- Answers Phase 0's business questions directly against the loaded database.
-- Section A: core queries (aggregation, joins, GROUP BY)
-- Section B: advanced queries (CTEs, window functions) — skill showcase
-- =============================================================================


-- =============================================================================
-- SECTION A — CORE QUERIES
-- =============================================================================

-- -----------------------------------------------------------------------------
-- A1. Revenue by department
-- Business question: "Which departments generate the most revenue?"
-- Joins billing -> admissions to attribute revenue to a department, since
-- billing itself has no department column (correctly normalized — department
-- belongs to admissions, not billing).
-- -----------------------------------------------------------------------------
SELECT
    a.department,
    COUNT(DISTINCT b.bill_id)      AS total_bills,
    SUM(b.amount)                  AS total_revenue,
    ROUND(AVG(b.amount), 2)        AS avg_bill_amount
FROM billing b
JOIN admissions a ON b.admission_id = a.admission_id
GROUP BY a.department
ORDER BY total_revenue DESC;


-- -----------------------------------------------------------------------------
-- A2. Doctor workload — appointment volume per doctor
-- Business question: "Am I overloaded compared to peers?" (Doctor stakeholder)
-- -----------------------------------------------------------------------------
SELECT
    d.doctor_id,
    d.first_name || ' ' || d.last_name  AS doctor_name,
    d.department,
    COUNT(ap.appointment_id)            AS total_appointments,
    SUM(CASE WHEN ap.status = 'Completed' THEN 1 ELSE 0 END) AS completed,
    SUM(CASE WHEN ap.status = 'Cancelled' THEN 1 ELSE 0 END) AS cancelled,
    SUM(CASE WHEN ap.status = 'No-show'   THEN 1 ELSE 0 END) AS no_shows
FROM doctors d
LEFT JOIN appointments ap ON d.doctor_id = ap.doctor_id
GROUP BY d.doctor_id, d.first_name, d.last_name, d.department
ORDER BY total_appointments DESC;


-- -----------------------------------------------------------------------------
-- A3. Average length of stay by department
-- Business question: "Are we overstaffed or understaffed anywhere?"
-- Only considers discharged patients (length_of_stay is NULL for still-admitted)
-- -----------------------------------------------------------------------------
SELECT
    department,
    COUNT(*)                                             AS discharged_admissions,
    ROUND(AVG(discharge_date - admission_date), 1)        AS avg_length_of_stay_days,
    MAX(discharge_date - admission_date)                  AS max_length_of_stay_days
FROM admissions
WHERE discharge_date IS NOT NULL
GROUP BY department
ORDER BY avg_length_of_stay_days DESC;


-- -----------------------------------------------------------------------------
-- A4. Insurance claim approval rate by provider
-- Business question: "Which insurance payers reimburse slowest / least reliably?"
-- -----------------------------------------------------------------------------

-- A4. Insurance Claim Approval Rate by Provider
-- Approval rate calculated using decided claims only.

SELECT
    insurance_provider,

    COUNT(*) AS total_claims,

    COUNT(*) FILTER (
        WHERE claim_status = 'Approved'
    ) AS approved_claims,

    COUNT(*) FILTER (
        WHERE claim_status = 'Rejected'
    ) AS rejected_claims,

    COUNT(*) FILTER (
        WHERE claim_status = 'Pending'
    ) AS pending_claims,

    ROUND(
        100.0 * COUNT(*) FILTER (
            WHERE claim_status = 'Approved'
        )
        / NULLIF(
            COUNT(*) FILTER (
                WHERE claim_status IN ('Approved', 'Rejected')
            ), 0
        ),
        1
    ) AS approval_rate_pct

FROM insurance_claims
GROUP BY insurance_provider
ORDER BY approval_rate_pct ASC NULLS LAST;



-- -----------------------------------------------------------------------------
-- A5. Lab turnaround time by test type
-- Business question: "Which tests are backlogged?" (Lab Management stakeholder)
-- -----------------------------------------------------------------------------

-- A5. Lab turnaround time by test type
-- Separates completed tests from pending tests.


-- A5. Lab Turnaround Time by Test Type
-- Completed results: Normal or Abnormal
-- Pending results are excluded from turnaround averages.

SELECT
    test_name,

    COUNT(*) AS total_tests,

    COUNT(*) FILTER (
        WHERE result_status IN ('Normal', 'Abnormal')
    ) AS completed_tests,

    COUNT(*) FILTER (
        WHERE result_status = 'Pending'
    ) AS pending_tests,

    ROUND(
        AVG(turnaround_hours) FILTER (
            WHERE result_status IN ('Normal', 'Abnormal')
        ), 1
    ) AS avg_turnaround_hours,

    ROUND(
        MAX(turnaround_hours) FILTER (
            WHERE result_status IN ('Normal', 'Abnormal')
        ), 1
    ) AS max_turnaround_hours

FROM lab_results
GROUP BY test_name
ORDER BY avg_turnaround_hours DESC NULLS LAST;




-- -----------------------------------------------------------------------------
-- A6. Appointment cancellation / no-show rate overall and by department
-- Business question: relates to "operational efficiency" from Phase 0
-- -----------------------------------------------------------------------------
SELECT
    d.department,
    COUNT(*)                                                                  AS total_appointments,
    ROUND(100.0 * SUM(CASE WHEN ap.status = 'Cancelled' THEN 1 ELSE 0 END) / COUNT(*), 1) AS cancellation_rate_pct,
    ROUND(100.0 * SUM(CASE WHEN ap.status = 'No-show'   THEN 1 ELSE 0 END) / COUNT(*), 1) AS no_show_rate_pct
FROM appointments ap
JOIN doctors d ON ap.doctor_id = d.doctor_id
GROUP BY d.department
ORDER BY cancellation_rate_pct DESC;


-- -----------------------------------------------------------------------------
-- A7. Patient volume by city
-- Business question: population-health / nearby-patients angle (Phase 0)
-- -----------------------------------------------------------------------------
SELECT
    city,
    COUNT(*)                          AS patient_count,
    ROUND(AVG(EXTRACT(YEAR FROM AGE(date_of_birth))), 1) AS avg_age
FROM patients
GROUP BY city
ORDER BY patient_count DESC;


-- =============================================================================
-- SECTION B — ADVANCED QUERIES (CTEs + Window Functions)
-- =============================================================================

-- -----------------------------------------------------------------------------
-- B1. "Which departments require additional resources?" — the Phase 0
-- showcase question. Combines patient volume, doctor workload,
-- cancellation rate, and length of stay into ONE ranked view using a CTE
-- for each metric, then joins them together.
-- -----------------------------------------------------------------------------

-- B1. Department Resource Analysis
-- Combines admission volume, doctor workload,
-- cancellation rates, and average length of stay.

WITH dept_volume AS (
    SELECT
        department,
        COUNT(*) AS admission_count
    FROM admissions
    GROUP BY department
),

dept_workload AS (
    SELECT
        d.department,
        COUNT(ap.appointment_id) AS appointment_count,
        COUNT(DISTINCT d.doctor_id) AS doctor_count
    FROM doctors d
    LEFT JOIN appointments ap
        ON d.doctor_id = ap.doctor_id
    GROUP BY d.department
),

dept_efficiency AS (
    SELECT
        department,
        ROUND(
            AVG(discharge_date - admission_date), 1
        ) AS avg_los
    FROM admissions
    WHERE discharge_date IS NOT NULL
    GROUP BY department
),

dept_cancellations AS (
    SELECT
        d.department,
        ROUND(
            100.0 * COUNT(*) FILTER (
                WHERE ap.status = 'Cancelled'
            ) / NULLIF(COUNT(*), 0),
            1
        ) AS cancellation_rate_pct
    FROM appointments ap
    JOIN doctors d
        ON ap.doctor_id = d.doctor_id
    GROUP BY d.department
)

SELECT
    w.department,
    COALESCE(v.admission_count, 0) AS admission_count,
    w.appointment_count,
    w.doctor_count,
    ROUND(
        w.appointment_count::numeric
        / NULLIF(w.doctor_count, 0),
        1
    ) AS appointments_per_doctor,
    COALESCE(c.cancellation_rate_pct, 0)
        AS cancellation_rate_pct,
    e.avg_los
FROM dept_workload w
LEFT JOIN dept_volume v
    ON w.department = v.department
LEFT JOIN dept_efficiency e
    ON w.department = e.department
LEFT JOIN dept_cancellations c
    ON w.department = c.department
ORDER BY appointments_per_doctor DESC;



-- -----------------------------------------------------------------------------
-- B2. Top 3 doctors by appointment volume WITHIN each department
-- (classic "top N per group" — genuinely hard without a window function)
-- -----------------------------------------------------------------------------
WITH doctor_counts AS (
    SELECT
        d.department,
        d.doctor_id,
        d.first_name || ' ' || d.last_name AS doctor_name,
        COUNT(ap.appointment_id) AS appointment_count,
        RANK() OVER (
            PARTITION BY d.department
            ORDER BY COUNT(ap.appointment_id) DESC
        ) AS dept_rank
    FROM doctors d
    LEFT JOIN appointments ap ON d.doctor_id = ap.doctor_id
    GROUP BY d.department, d.doctor_id, d.first_name, d.last_name
)
SELECT department, doctor_name, appointment_count, dept_rank
FROM doctor_counts
WHERE dept_rank <= 3
ORDER BY department, dept_rank;


-- -----------------------------------------------------------------------------
-- B3. Monthly revenue trend with month-over-month % change
-- (running comparison via LAG window function)
-- -----------------------------------------------------------------------------
WITH monthly_revenue AS (
    SELECT
        DATE_TRUNC('month', bill_date) AS month,
        SUM(amount) AS revenue
    FROM billing
    GROUP BY DATE_TRUNC('month', bill_date)
)
SELECT
    month,
    revenue,
    LAG(revenue) OVER (ORDER BY month) AS prev_month_revenue,
    ROUND(
        100.0 * (revenue - LAG(revenue) OVER (ORDER BY month))
        / NULLIF(LAG(revenue) OVER (ORDER BY month), 0), 1
    ) AS pct_change_from_prev_month
FROM monthly_revenue
ORDER BY month;


-- -----------------------------------------------------------------------------
-- B4. Each patient's total lifetime billing amount, and what % of the
-- HOSPITAL'S total revenue that represents (window function without GROUP BY
-- collapsing patient-level detail)
-- -----------------------------------------------------------------------------

-- B4. Top 20 patients by total lifetime billing
-- and percentage contribution to hospital revenue

WITH patient_revenue AS (
    SELECT
        p.patient_id,
        p.first_name || ' ' || p.last_name AS patient_name,
        SUM(b.amount) AS patient_total_billing
    FROM patients p
    JOIN billing b
        ON p.patient_id = b.patient_id
    GROUP BY
        p.patient_id,
        p.first_name,
        p.last_name
)

SELECT
    patient_id,
    patient_name,
    patient_total_billing,
    ROUND(
        100.0 * patient_total_billing
        / NULLIF(SUM(patient_total_billing) OVER (), 0),
        3
    ) AS pct_of_total_hospital_revenue
FROM patient_revenue
ORDER BY patient_total_billing DESC
LIMIT 20;
