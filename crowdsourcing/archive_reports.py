# SPDX-FileCopyrightText: 2025 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

import logging

from crowdsourcing.archive_manager import ArchiveManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_and_archive_reports() -> None:
    """Check if reports need to be archived and archive them if necessary."""
    try:
        logger.info("Starting report archival check")
        archive_manager = ArchiveManager()

        if archive_manager.needs_archival():
            logger.info("Archival threshold reached, starting archival process")
            doi = archive_manager.archive_reports()
            logger.info(f"Successfully archived reports. DOI: {doi}")
        else:
            logger.info("Archival threshold not reached, no action needed")

    except Exception as e:
        logger.error(f"Error during report archival: {e}")
        raise


if __name__ == "__main__":  # pragma: no cover
    check_and_archive_reports()
