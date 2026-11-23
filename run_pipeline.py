
"""
MediFlow Analytics - Pipeline Orchestrator (Phase 11)

Single entry point for the full ETL pipeline:

Extract -> Transform -> Load and Verify

Designed for unattended execution using Windows Task
Scheduler, cron, or another orchestration tool.

Exit codes:
    0 = Pipeline completed successfully
    1 = Pipeline failed

Usage:
    python run_pipeline.py
"""

import logging
import sys
import time
from datetime import datetime

from etl.extract import extract_all, ExtractionError
from etl.transform import transform_all
from etl.load import load_all, LoadError

logger = logging.getLogger("run_pipeline")


def run() -> int:
    """
    Execute the full ETL pipeline.

    Returns:
        0 on success
        1 on failure
    """
    start_time = time.time()
    run_started_at = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    logger.info("#" * 70)
    logger.info(
        "# MediFlow Analytics - Pipeline run started at %s",
        run_started_at,
    )
    logger.info("#" * 70)

    stage = "Extract"

    try:
        # Stage 1: Extract raw datasets.
        logger.info("Starting extraction")
        raw = extract_all()

        # Stage 2: Clean and transform datasets.
        stage = "Transform"
        logger.info("Starting transformation")
        clean = transform_all(raw)

        # Stage 3: Load and verify inside one transaction.
        stage = "Load and Verify"
        logger.info("Starting transactional load and verification")
        load_all(clean)

    except (ExtractionError, LoadError) as e:
        elapsed = round(time.time() - start_time, 1)

        logger.error("#" * 70)
        logger.error(
            "# PIPELINE FAILED at stage: %s",
            stage,
        )
        logger.error("# Reason: %s", e)
        logger.error(
            "# Elapsed time before failure: %ss",
            elapsed,
        )
        logger.error("#" * 70)

        return 1

    except Exception as e:
        elapsed = round(time.time() - start_time, 1)

        logger.error("#" * 70)
        logger.error(
            "# PIPELINE FAILED at stage: %s "
            "(UNEXPECTED ERROR)",
            stage,
        )
        logger.error(
            "# Reason: %s: %s",
            type(e).__name__,
            e,
        )
        logger.error(
            "# Elapsed time before failure: %ss",
            elapsed,
        )
        logger.exception("Full traceback:")
        logger.error("#" * 70)

        return 1

    elapsed = round(time.time() - start_time, 1)

    logger.info("#" * 70)
    logger.info(
        "# PIPELINE SUCCEEDED - completed in %ss",
        elapsed,
    )

    logger.info(
        "# Rows loaded: %s",
        ", ".join(
            f"{table}={len(df):,}"
            for table, df in clean.items()
        ),
    )

    logger.info("#" * 70)

    return 0


if __name__ == "__main__":
    exit_code = run()
    sys.exit(exit_code)
