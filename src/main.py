"""Main entry point for OmniFeed ETL pipeline.

This module provides the CLI entry point for running the ETL pipeline
locally or in GitHub Actions.
"""

import asyncio
import logging
import sys

from src.etl.pipeline import run_pipeline


def setup_logging() -> None:
    """Configure logging for the application."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )


async def main() -> int:
    """Main entry point."""
    setup_logging()
    logger = logging.getLogger(__name__)

    try:
        logger.info("Starting OmniFeed ETL pipeline")
        summary = await run_pipeline()

        logger.info("Pipeline completed successfully")
        logger.info(f"Summary: {summary}")

        return 0
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
