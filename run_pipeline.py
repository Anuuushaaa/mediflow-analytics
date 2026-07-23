"""
MediFlow Analytics — Pipeline Orchestrator (Phase 11)

Single entry point for the full ETL pipeline: Extract -> Transform ->
Load -> Verify. Designed to run unattended (e.g. via Windows Task
Scheduler or cron) with proper exit codes and a clear pass/fail summary
at the end of the log.

Exit codes:
    0 = pipeline completed successfully
    1 = pipeline failed (see logs/etl_pipeline.log and the summary
        printed at the end of this run for exactly which stage failed)

Usage:
    python run_pipeline.py
"""

import logging
import sys
import time
from datetime import datetime

from etl.extract import extract_all, ExtractionError
from etl.transform import transform_all
from etl.load import load_all, verify_load, LoadError

logger = logging.getLogger("run_pipeline")


def run() -> int:
    """Runs the full pipeline. Returns an exit code (0 = success, 1 = failure)."""
    start_time = time.time()
    run_started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    logger.info("#" * 70)
    logger.info(f"# MediFlow Analytics — Pipeline run started at {run_started_at}")
    logger.info("#" * 70)

    stage = "Extract"
    try:
        raw = extract_all()

        stage = "Transform"
        clean = transform_all(raw)

        stage = "Load"
        load_all(clean)

        stage = "Verify"
        verify_load(clean)

    except (ExtractionError, LoadError) as e:
        elapsed = round(time.time() - start_time, 1)
        logger.error("#" * 70)
        logger.error(f"# PIPELINE FAILED at stage: {stage}")
        logger.error(f"# Reason: {e}")
        logger.error(f"# Elapsed time before failure: {elapsed}s")
        logger.error("#" * 70)
        return 1

    except Exception as e:
        # Catch-all for anything unexpected (e.g. a bug we haven't
        # anticipated) — we still want a clean failure summary and exit
        # code rather than a bare, unattended crash with no context.
        elapsed = round(time.time() - start_time, 1)
        logger.error("#" * 70)
        logger.error(f"# PIPELINE FAILED at stage: {stage} (UNEXPECTED ERROR)")
        logger.error(f"# Reason: {type(e).__name__}: {e}")
        logger.error(f"# Elapsed time before failure: {elapsed}s")
        logger.error("#" * 70)
        logger.exception("Full traceback:")
        return 1

    elapsed = round(time.time() - start_time, 1)
    logger.info("#" * 70)
    logger.info(f"# PIPELINE SUCCEEDED — completed in {elapsed}s")
    logger.info(f"# Rows loaded: " + ", ".join(f"{k}={len(v):,}" for k, v in clean.items()))
    logger.info("#" * 70)
    return 0


if __name__ == "__main__":
    exit_code = run()
    sys.exit(exit_code)