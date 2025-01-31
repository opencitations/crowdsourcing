#!/usr/bin/env python3
import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler

from crowdsourcing.meta_runner import process_meta_issues
from dotenv import load_dotenv

# Get the absolute path to the .env file
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
load_dotenv(dotenv_path=env_path, override=True)

# Create logs directory if it doesn't exist
os.makedirs("logs", exist_ok=True)

# Configure logging
log_file = os.path.join("logs", "meta_process.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        RotatingFileHandler(log_file, maxBytes=1024 * 1024, backupCount=5),  # 1MB
        logging.StreamHandler(),
    ],
)


def main():
    logger = logging.getLogger(__name__)
    start_time = datetime.now()

    logger.info("Starting meta process run")
    try:
        process_meta_issues()
        logger.info(
            f"Meta process completed successfully in {datetime.now() - start_time}"
        )
    except Exception as e:
        logger.error(f"Meta process failed: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
