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

import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import yaml
from crowdsourcing.archive_manager import ArchiveManager
from crowdsourcing.archive_reports import check_and_archive_reports


class TestArchiveReports(unittest.TestCase):
    def setUp(self):
        """Set up test environment before each test."""
        # Create a temporary directory for test files
        self.test_dir = tempfile.mkdtemp()
        self.reports_dir = os.path.join(self.test_dir, "docs/validation_reports")
        os.makedirs(self.reports_dir)

        # Create test config file
        self.config = {
            "validation_reports": {
                "max_reports_before_archive": 3,
                "reports_dir": self.reports_dir,
                "index_file": os.path.join(self.reports_dir, "index.json"),
            },
            "zenodo": {
                "metadata_template": {
                    "title": "Test Archive",
                    "description": "Test Description",
                    "creators": [{"name": "Test Creator"}],
                    "access_right": "open",
                    "upload_type": "dataset",
                    "license": "CC0-1.0",
                }
            },
        }
        self.config_path = os.path.join(self.test_dir, "test_config.yaml")
        with open(self.config_path, "w") as f:
            yaml.dump(self.config, f)

        # Set environment variables for testing
        self.env_patcher = patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "development",
                "ZENODO_SANDBOX": "fake-token",
            },
        )
        self.env_patcher.start()

        # Patch ArchiveManager to use our test config
        self.archive_manager_patcher = patch(
            "crowdsourcing.archive_reports.ArchiveManager",
            return_value=ArchiveManager(config_path=self.config_path),
        )
        self.archive_manager_patcher.start()

    def tearDown(self):
        """Clean up after each test."""
        self.archive_manager_patcher.stop()
        self.env_patcher.stop()
        shutil.rmtree(self.test_dir)

    @patch("crowdsourcing.archive_reports.logger")
    def test_check_and_archive_reports_no_reports(self, mock_logger):
        """Test check_and_archive_reports when there are no reports to archive."""
        # Initialize archive manager and run check
        check_and_archive_reports()

        # Verify logging
        mock_logger.info.assert_any_call("Starting report archival check")
        mock_logger.info.assert_any_call(
            "Archival threshold not reached, no action needed"
        )

    @patch("crowdsourcing.archive_reports.logger")
    def test_check_and_archive_reports_below_threshold(self, mock_logger):
        """Test check_and_archive_reports when number of reports is below threshold."""
        # Initialize archive manager
        archive_manager = ArchiveManager(config_path=self.config_path)

        # Add some reports (less than threshold)
        for i in range(2):  # threshold is 3
            report_name = f"validation_issue_{i}.html"
            report_path = os.path.join(self.reports_dir, report_name)
            with open(report_path, "w") as f:
                f.write(f"Test report {i}")
            archive_manager.add_report(
                report_name, f"https://example.com/{report_name}"
            )

        # Run check
        check_and_archive_reports()

        # Verify logging
        mock_logger.info.assert_any_call("Starting report archival check")
        mock_logger.info.assert_any_call(
            "Archival threshold not reached, no action needed"
        )

    @patch("crowdsourcing.archive_reports.logger")
    @patch("crowdsourcing.zenodo_utils.create_deposition_resource")
    @patch("crowdsourcing.zenodo_utils.get_zenodo_token")
    @patch("requests.put")
    @patch("requests.post")
    def test_check_and_archive_reports_above_threshold(
        self, mock_post, mock_put, mock_get_token, mock_create_deposition, mock_logger
    ):
        """Test check_and_archive_reports when number of reports is above threshold."""
        # Setup mocks
        mock_response = {"id": "123", "links": {"bucket": "http://bucket-url"}}
        mock_deposition_response = MagicMock()
        mock_deposition_response.json.return_value = mock_response
        mock_deposition_response.raise_for_status = MagicMock()

        mock_publish_response = MagicMock()
        mock_publish_response.json.return_value = {"doi": "10.5281/zenodo.123"}
        mock_publish_response.raise_for_status = MagicMock()
        mock_post.side_effect = [mock_deposition_response, mock_publish_response]

        mock_get_token.return_value = "fake-token"
        mock_put.return_value.raise_for_status = MagicMock()

        # Mock ArchiveManager to use our test config
        with patch(
            "crowdsourcing.archive_reports.ArchiveManager"
        ) as mock_archive_manager:
            mock_instance = mock_archive_manager.return_value
            mock_instance.needs_archival.return_value = True
            mock_instance.archive_reports.return_value = "10.5281/zenodo.123"

            # Run check
            check_and_archive_reports()

            # Verify logging
            mock_logger.info.assert_has_calls(
                [
                    unittest.mock.call("Starting report archival check"),
                    unittest.mock.call(
                        "Archival threshold reached, starting archival process"
                    ),
                    unittest.mock.call(
                        "Successfully archived reports. DOI: 10.5281/zenodo.123"
                    ),
                ],
                any_order=False,
            )

    @patch("crowdsourcing.archive_reports.logger")
    def test_check_and_archive_reports_error(self, mock_logger):
        """Test check_and_archive_reports when an error occurs."""
        # Create a mock ArchiveManager that raises an exception
        with patch("crowdsourcing.archive_reports.ArchiveManager") as mock_manager:
            mock_instance = mock_manager.return_value
            mock_instance.needs_archival.side_effect = Exception("Test error")

            # Run check
            with self.assertRaises(Exception):
                check_and_archive_reports()

            # Verify logging
            mock_logger.info.assert_called_with("Starting report archival check")
            mock_logger.error.assert_called_with(
                "Error during report archival: Test error"
            )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
