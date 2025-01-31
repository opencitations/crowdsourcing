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
from datetime import datetime

import yaml
from crowdsourcing.archive_manager import ArchiveManager
import requests


class TestArchiveManager(unittest.TestCase):
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
                "archive_batch_size": 2,
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
                    "publication_date": datetime.now().strftime("%Y-%m-%d"),
                    "prereserve_doi": True,
                    "license": "CC0-1.0",
                    "keywords": ["OpenCitations", "crowdsourcing", "test"],
                }
            },
        }
        self.config_path = os.path.join(self.test_dir, "test_config.yaml")
        with open(self.config_path, "w") as f:
            yaml.dump(self.config, f)

        # Initialize archive manager with test config
        self.manager = ArchiveManager(config_path=self.config_path)

    def tearDown(self):
        """Clean up after each test."""
        shutil.rmtree(self.test_dir)

    def test_init_creates_index(self):
        """Test that initialization creates the index file if it doesn't exist."""
        self.assertTrue(os.path.exists(self.manager.index_path))
        with open(self.manager.index_path) as f:
            index_data = json.load(f)
        self.assertEqual(index_data["github_reports"], {})
        self.assertEqual(index_data["zenodo_reports"], {})
        self.assertIsNone(index_data["last_archive"])

    def test_add_report(self):
        """Test adding a new report to the index."""
        report_name = "test_report.html"
        github_url = "https://example.com/report"
        self.manager.add_report(report_name, github_url)

        with open(self.manager.index_path) as f:
            index_data = json.load(f)
        self.assertEqual(index_data["github_reports"][report_name], github_url)

    def test_get_report_url_github(self):
        """Test getting URL for a report that's on GitHub."""
        report_name = "test_report.html"
        github_url = "https://example.com/report"
        self.manager.add_report(report_name, github_url)

        url = self.manager.get_report_url(report_name)
        self.assertEqual(url, github_url)

    @patch.dict(
        os.environ, {"ENVIRONMENT": "development", "ZENODO_SANDBOX": "fake-token"}
    )
    @patch("crowdsourcing.zenodo_utils.create_deposition_resource")
    @patch("crowdsourcing.zenodo_utils.get_zenodo_token")
    @patch("requests.put")
    @patch("requests.post")
    def test_archive_reports(
        self, mock_post, mock_put, mock_get_token, mock_create_deposition
    ):
        """Test archiving reports to Zenodo."""
        # Setup mocks
        mock_response = {"id": "123", "links": {"bucket": "http://bucket-url"}}

        # Mock the POST request to create deposition
        mock_deposition_response = MagicMock()
        mock_deposition_response.json.return_value = mock_response
        mock_deposition_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_deposition_response

        # Mock the publish response
        mock_publish_response = MagicMock()
        mock_publish_response.json.return_value = {"doi": "10.5281/zenodo.123"}
        mock_publish_response.raise_for_status = MagicMock()
        mock_post.side_effect = [mock_deposition_response, mock_publish_response]

        mock_get_token.return_value = "fake-token"
        mock_put.return_value.raise_for_status = MagicMock()

        # Create test reports
        for i in range(4):
            report_name = f"validation_issue_{i}.html"
            report_path = os.path.join(self.reports_dir, report_name)
            with open(report_path, "w") as f:
                f.write(f"Test report {i}")
            self.manager.add_report(report_name, f"https://example.com/{report_name}")

        # Archive should be triggered after 4th report (max is 3)
        with open(self.manager.index_path) as f:
            index_data = json.load(f)

        # Verify that 2 oldest reports were archived (batch_size is 2)
        self.assertEqual(len(index_data["github_reports"]), 2)
        self.assertEqual(len(index_data["zenodo_reports"]), 2)
        self.assertTrue(
            all(
                report_data["doi"].startswith("https://doi.org/")
                and report_data["url"].startswith("https://sandbox.zenodo.org/record/")
                for report_data in index_data["zenodo_reports"].values()
            )
        )

    def test_get_report_url_zenodo(self):
        """Test getting URL for a report that's been archived to Zenodo."""
        # Add a report to zenodo_reports directly
        report_name = "archived_report.html"
        zenodo_data = {
            "url": "https://sandbox.zenodo.org/record/123/files/archived_report.html",
            "doi": "https://doi.org/10.5281/zenodo.123",
        }

        index_data = self.manager._load_index()
        index_data["zenodo_reports"][report_name] = zenodo_data
        self.manager._save_index(index_data)

        url = self.manager.get_report_url(report_name)
        self.assertEqual(url, zenodo_data["url"])  # Should return the direct URL

    def test_get_report_url_not_found(self):
        """Test getting URL for a non-existent report."""
        url = self.manager.get_report_url("non_existent.html")
        self.assertIsNone(url)

    def test_init_creates_directories(self):
        """Test that initialization creates necessary directories."""
        # Remove test directories
        shutil.rmtree(self.test_dir)

        # Create config file with test paths
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, "w") as f:
            yaml.dump(self.config, f)

        # Reinitialize manager (should create all necessary directories and files)
        self.manager = ArchiveManager(config_path=self.config_path)

        # Check that directories were created
        self.assertTrue(os.path.exists(self.reports_dir))
        self.assertTrue(os.path.exists(os.path.dirname(self.manager.index_path)))
        self.assertTrue(os.path.exists(self.config_path))

    def test_add_report_creates_directories(self):
        """Test that adding a report creates necessary directories if they don't exist."""
        # Remove test directories
        shutil.rmtree(self.test_dir)

        # Add a report (should create directories)
        self.manager.add_report("test.html", "http://example.com/test")

        # Check that directories were created
        self.assertTrue(os.path.exists(self.reports_dir))
        self.assertTrue(os.path.exists(self.manager.index_path))

    def test_archive_reports_no_reports(self):
        """Test that archive_reports returns None when there are no reports to archive."""
        # Initialize empty index
        self.manager._init_index()

        # Call archive_reports with no reports
        result = self.manager.archive_reports()

        # Verify that None is returned
        self.assertIsNone(result)

        # Verify index remains unchanged
        with open(self.manager.index_path) as f:
            index_data = json.load(f)
        self.assertEqual(index_data["github_reports"], {})
        self.assertEqual(index_data["zenodo_reports"], {})
        self.assertIsNone(index_data["last_archive"])

    @patch.dict(
        os.environ, {"ENVIRONMENT": "development", "ZENODO_SANDBOX": "fake-token"}
    )
    @patch("crowdsourcing.zenodo_utils.create_deposition_resource")
    @patch("crowdsourcing.zenodo_utils.get_zenodo_token")
    @patch("crowdsourcing.archive_manager.logger")
    def test_archive_reports_error(
        self, mock_logger, mock_get_token, mock_create_deposition
    ):
        """Test that archive_reports properly handles and logs errors."""
        # Setup error to be raised
        test_error = requests.exceptions.HTTPError(
            "403 Client Error: FORBIDDEN for url: https://sandbox.zenodo.org/api/deposit/depositions"
        )
        mock_create_deposition.side_effect = test_error

        # Create a test report to archive
        report_name = "test_report.html"
        report_path = os.path.join(self.reports_dir, report_name)
        with open(report_path, "w") as f:
            f.write("Test report")
        self.manager.add_report(report_name, "http://example.com/report")

        # Verify that exception is raised and error is logged
        with self.assertRaises(requests.exceptions.HTTPError) as context:
            self.manager.archive_reports()

        self.assertEqual(
            str(context.exception),
            "403 Client Error: FORBIDDEN for url: https://sandbox.zenodo.org/api/deposit/depositions",
        )
        mock_logger.error.assert_called_once_with(
            "Failed to archive reports: 403 Client Error: FORBIDDEN for url: https://sandbox.zenodo.org/api/deposit/depositions"
        )

        # Verify that index remains unchanged
        with open(self.manager.index_path) as f:
            index_data = json.load(f)
        self.assertIn(report_name, index_data["github_reports"])
        self.assertEqual(len(index_data["zenodo_reports"]), 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
