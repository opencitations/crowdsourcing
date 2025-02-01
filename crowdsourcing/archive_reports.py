#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright 2025 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# Permission to use, copy, modify, and/or distribute this software for any purpose
# with or without fee is hereby granted, provided that the above copyright notice
# and this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED 'AS IS' AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
# REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND
# FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT, INDIRECT,
# OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS OF USE,
# DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS
# ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS
# SOFTWARE.

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
