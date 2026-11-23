
"""
MediFlow Analytics - Main ETL Pipeline.

Pipeline stages:
1. Extract raw healthcare datasets.
2. Clean and transform datasets.
3. Load data into PostgreSQL.
4. Log execution results.

Supported load modes:
- full (default): Truncate and reload all tables.
- incremental: Insert new records, update changed records,
  and preserve unchanged or missing source records.

Environment variables:
- MEDIFLOW_CONFIG: Path to YAML configuration file.
- MEDIFLOW_LOAD_MODE: "full" or "incremental".
"""

import logging
import os
import sys
import time
from datetime import datetime

from etl.extract import extract_all
from etl.transform import transform_all
from etl.load import load_all, LoadError
from etl.incremental_load import (
    incremental_load_all,
    IncrementalLoadError,
)


# --------------------------------------------------
# Logging configuration
# --------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger("mediflow.pipeline")


# --------------------------------------------------
# Main ETL pipeline
# --------------------------------------------------

def run():
    """
    Execute the complete MediFlow ETL pipeline.

    Returns:
        0: Pipeline completed successfully.
        1: Pipeline failed.
    """

    start_time = time.time()

    config_path = os.getenv(
        "MEDIFLOW_CONFIG",
        "config/config.yaml",
    )

    load_mode = os.getenv(
        "MEDIFLOW_LOAD_MODE",
        "full",
    ).strip().lower()

    logger.info("=" * 60)
    logger.info("MediFlow Analytics ETL Pipeline")
    logger.info("Started at: %s", datetime.now().isoformat())
    logger.info("Configuration: %s", config_path)
    logger.info("Load mode: %s", load_mode.upper())
    logger.info("=" * 60)

    try:
        # Validate mode before extracting any data.
        if load_mode not in ("full", "incremental"):
            raise ValueError(
                f"Unsupported MEDIFLOW_LOAD_MODE: {load_mode}. "
                "Expected 'full' or 'incremental'."
            )

        # ------------------------------------------
        # Stage 1: Extract
        # ------------------------------------------

        logger.info("STAGE 1: Extracting raw datasets")

        raw = extract_all(
            config_path=config_path
        )

        logger.info(
            "Extraction completed: %s datasets",
            len(raw),
        )

        # ------------------------------------------
        # Stage 2: Transform
        # ------------------------------------------

        logger.info("STAGE 2: Transforming datasets")

        clean = transform_all(raw)

        logger.info(
            "Transformation completed: %s datasets",
            len(clean),
        )

        # ------------------------------------------
        # Stage 3: Load
        # ------------------------------------------

        logger.info("STAGE 3: Loading into PostgreSQL")

        if load_mode == "full":

            logger.info(
                "Executing FULL REFRESH load"
            )

            load_all(
                clean,
                config_path=config_path,
            )

        elif load_mode == "incremental":

            logger.info(
                "Executing INCREMENTAL load"
            )

            incremental_load_all(
                clean,
                config_path=config_path,
            )

        logger.info(
            "Database loading completed successfully"
        )

        # ------------------------------------------
        # Stage 4: Execution summary
        # ------------------------------------------

        elapsed = time.time() - start_time

        logger.info("=" * 60)
        logger.info("ETL PIPELINE COMPLETED SUCCESSFULLY")
        logger.info("Load mode: %s", load_mode.upper())
        logger.info("Execution time: %.2f seconds", elapsed)

        for table, df in clean.items():
            logger.info(
                "%s: %s cleaned source records",
                table,
                len(df),
            )

        logger.info("=" * 60)

        return 0

    except (LoadError, IncrementalLoadError) as exc:

        logger.exception(
            "Database loading failed: %s",
            exc,
        )

        return 1

    except Exception as exc:

        logger.exception(
            "ETL pipeline failed: %s",
            exc,
        )

        return 1


# --------------------------------------------------
# Entry point
# --------------------------------------------------

if __name__ == "__main__":
    sys.exit(run())
