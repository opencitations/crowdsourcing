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

import os
import shutil
import time
import unittest
from unittest.mock import patch, Mock, MagicMock
import csv
import json
from meta_runner import (
    get_closed_issues,
    store_meta_input,
    get_ingestion_dirs,
    check_triplestore_connection,
    process_single_issue,
    update_issue_labels,
    process_meta_issues,
)
import requests
import yaml


class TestMetaRunner(unittest.TestCase):
    def setUp(self):
        # Create a temporary environment variable for testing
        os.environ["GH_TOKEN"] = "test_token"
        os.environ["GITHUB_REPOSITORY"] = "test/repo"

    def tearDown(self):
        # Clean up any created directories
        if os.path.exists("crowdsourcing_ingestion_data"):
            shutil.rmtree("crowdsourcing_ingestion_data")
        # Remove environment variables
        del os.environ["GH_TOKEN"]
        del os.environ["GITHUB_REPOSITORY"]

    @patch("time.strftime")
    def test_get_ingestion_dirs(self, mock_strftime):
        # Mock the current date
        mock_strftime.return_value = "2024_03"

        # Call the function
        base_dir, metadata_dir, citations_dir = get_ingestion_dirs()

        # Check the returned paths
        self.assertEqual(
            base_dir, os.path.join("crowdsourcing_ingestion_data", "2024_03")
        )
        self.assertEqual(metadata_dir, os.path.join(base_dir, "metadata"))
        self.assertEqual(citations_dir, os.path.join(base_dir, "citations"))

        # Check that directories were created
        self.assertTrue(os.path.exists(metadata_dir))
        self.assertTrue(os.path.exists(citations_dir))

    @patch("requests.get")
    def test_get_closed_issues_success(self, mock_get):
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"body": "test body 1", "number": 1},
            {"body": "test body 2", "number": 2},
        ]
        mock_get.return_value = mock_response

        # Call the function
        issues = get_closed_issues()

        # Verify the results
        self.assertEqual(len(issues), 2)
        self.assertEqual(issues[0]["body"], "test body 1")
        self.assertEqual(issues[0]["number"], "1")

        # Verify the API call
        mock_get.assert_called_once_with(
            "https://api.github.com/repos/test/repo/issues",
            params={"state": "closed", "labels": "to be processed"},
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": "Bearer test_token",
            },
            timeout=30,
        )

    @patch("requests.get")
    def test_get_closed_issues_404(self, mock_get):
        # Mock 404 response
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        # Call the function
        issues = get_closed_issues()

        # Verify empty result
        self.assertEqual(issues, [])

    @patch("requests.get")
    def test_get_closed_issues_rate_limit(self, mock_get):
        # Mock rate limit response
        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.headers = {
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(int(time.time()) + 1),
        }
        mock_get.return_value = mock_response

        # Call the function
        issues = get_closed_issues()

        # Verify empty result and multiple attempts
        self.assertEqual(issues, [])
        self.assertEqual(mock_get.call_count, 3)  # MAX_RETRIES

    @patch("requests.get")
    def test_get_closed_issues_unexpected_status(self, mock_get):
        """Test handling of unexpected HTTP status codes."""
        # Mock response with unexpected status code
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_get.return_value = mock_response

        # Call the function
        issues = get_closed_issues()

        # Verify empty result after all retries
        self.assertEqual(issues, [])
        self.assertEqual(mock_get.call_count, 3)  # Should retry MAX_RETRIES times

    @patch("requests.get")
    @patch("time.sleep")  # Mock sleep to speed up test
    def test_get_closed_issues_request_exception(self, mock_sleep, mock_get):
        """Test handling of request exceptions with retries."""
        # Mock get to raise exception
        mock_get.side_effect = requests.RequestException("Connection error")

        # Verify exception is raised after all retries
        with self.assertRaises(RuntimeError) as context:
            get_closed_issues()

        self.assertEqual(
            str(context.exception), "Failed to fetch issues after 3 attempts"
        )
        self.assertEqual(mock_get.call_count, 3)  # Should retry MAX_RETRIES times
        self.assertEqual(
            mock_sleep.call_count, 2
        )  # Should sleep RETRY_DELAY times (attempts - 1)
        mock_sleep.assert_called_with(5)  # Verify sleep duration

    @patch("requests.get")
    def test_get_closed_issues_key_error(self, mock_get):
        """Test handling of KeyError in response parsing."""
        # Mock response with missing required key
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"number": 1}]  # Missing 'body' key
        mock_get.return_value = mock_response

        # Verify exception is raised after all retries
        with self.assertRaises(RuntimeError) as context:
            get_closed_issues()

        self.assertEqual(
            str(context.exception), "Failed to fetch issues after 3 attempts"
        )
        self.assertEqual(mock_get.call_count, 3)  # Should retry MAX_RETRIES times

    def test_store_meta_input_success(self):
        # Create test data
        issues = [
            {
                "body": "id,title\n1,Test Title\n===###===@@@===citing,cited\n123,456",
                "number": "1",
            }
        ]

        # Call the function
        store_meta_input(issues)

        # Get the created directories
        base_dir = os.path.join("crowdsourcing_ingestion_data", time.strftime("%Y_%m"))
        metadata_file = os.path.join(base_dir, "metadata", "0.csv")
        citations_file = os.path.join(base_dir, "citations", "0.csv")

        # Check that files were created
        self.assertTrue(os.path.exists(metadata_file))
        self.assertTrue(os.path.exists(citations_file))

        # Verify metadata content
        with open(metadata_file, "r") as f:
            metadata = list(csv.DictReader(f))
            self.assertEqual(len(metadata), 1)
            self.assertEqual(metadata[0]["id"], "1")
            self.assertEqual(metadata[0]["title"], "Test Title")

        # Verify citations content
        with open(citations_file, "r") as f:
            citations = list(csv.DictReader(f))
            self.assertEqual(len(citations), 1)
            self.assertEqual(citations[0]["citing"], "123")
            self.assertEqual(citations[0]["cited"], "456")

    def test_store_meta_input_invalid_separator(self):
        # Create test data with invalid separator
        issues = [
            {
                "body": "id,title\n1,Test Title\nInvalid Separator\nciting,cited\n123,456",
                "number": "1",
            }
        ]

        # Call the function
        store_meta_input(issues)

        # Check that no files were created
        base_dir = os.path.join("crowdsourcing_ingestion_data", time.strftime("%Y_%m"))
        metadata_dir = os.path.join(base_dir, "metadata")
        citations_dir = os.path.join(base_dir, "citations")

        self.assertTrue(os.path.exists(metadata_dir))  # Directories should exist
        self.assertTrue(os.path.exists(citations_dir))
        self.assertEqual(len(os.listdir(metadata_dir)), 0)  # But should be empty
        self.assertEqual(len(os.listdir(citations_dir)), 0)

    def test_store_meta_input_empty_sections(self):
        # Create test data with empty sections
        issues = [{"body": "\n===###===@@@===\n", "number": "1"}]

        # Call the function
        store_meta_input(issues)

        # Check that no files were created
        base_dir = os.path.join("crowdsourcing_ingestion_data", time.strftime("%Y_%m"))
        metadata_dir = os.path.join(base_dir, "metadata")
        citations_dir = os.path.join(base_dir, "citations")

        self.assertTrue(os.path.exists(metadata_dir))
        self.assertTrue(os.path.exists(citations_dir))
        self.assertEqual(len(os.listdir(metadata_dir)), 0)
        self.assertEqual(len(os.listdir(citations_dir)), 0)

    def test_store_meta_input_empty_citations_section(self):
        # Test with empty citations section
        issues = [{"body": "id,title\n1,Test Title\n===###===@@@===\n", "number": "1"}]

        # Call the function
        store_meta_input(issues)

        # Check that no files were created since we should have continued
        base_dir = os.path.join("crowdsourcing_ingestion_data", time.strftime("%Y_%m"))
        metadata_dir = os.path.join(base_dir, "metadata")
        citations_dir = os.path.join(base_dir, "citations")
        self.assertEqual(len(os.listdir(metadata_dir)), 0)
        self.assertEqual(len(os.listdir(citations_dir)), 0)

    def test_store_meta_input_empty_metadata_records(self):
        # Test with empty metadata records after parsing
        issues = [
            {"body": "id,title\n===###===@@@===citing,cited\n123,456", "number": "1"}
        ]

        # Call the function
        store_meta_input(issues)

        # Check that no files were created since we should have continued
        base_dir = os.path.join("crowdsourcing_ingestion_data", time.strftime("%Y_%m"))
        metadata_dir = os.path.join(base_dir, "metadata")
        citations_dir = os.path.join(base_dir, "citations")
        self.assertEqual(len(os.listdir(metadata_dir)), 0)
        self.assertEqual(len(os.listdir(citations_dir)), 0)

    def test_store_meta_input_empty_citation_records(self):
        # Test with empty citation records after parsing
        issues = [
            {
                "body": "id,title\n1,Test Title\n===###===@@@===citing,cited\n",
                "number": "1",
            }
        ]

        # Call the function
        store_meta_input(issues)

        # Check that no files were created since we should have continued
        base_dir = os.path.join("crowdsourcing_ingestion_data", time.strftime("%Y_%m"))
        metadata_dir = os.path.join(base_dir, "metadata")
        citations_dir = os.path.join(base_dir, "citations")
        self.assertEqual(len(os.listdir(metadata_dir)), 0)
        self.assertEqual(len(os.listdir(citations_dir)), 0)

    def test_store_meta_input_key_error(self):
        # Test with missing required key that will raise KeyError
        issues = [{"wrong_key": "value"}]  # Missing 'body' key

        # Call the function
        store_meta_input(issues)

        # Check that no files were created due to KeyError
        base_dir = os.path.join("crowdsourcing_ingestion_data", time.strftime("%Y_%m"))
        metadata_dir = os.path.join(base_dir, "metadata")
        citations_dir = os.path.join(base_dir, "citations")
        self.assertEqual(len(os.listdir(metadata_dir)), 0)
        self.assertEqual(len(os.listdir(citations_dir)), 0)

    def test_store_meta_input_thousand_record_limit(self):
        # Create test data with more than 1000 records
        metadata_rows = ["1,Test Title"] * 1200  # 1200 identical rows
        citation_rows = ["123,456"] * 1200  # 1200 identical rows

        issues = [
            {
                "body": f"id,title\n{chr(10).join(metadata_rows)}\n===###===@@@===citing,cited\n{chr(10).join(citation_rows)}",
                "number": "1",
            }
        ]

        # Call the function
        store_meta_input(issues)

        # Get the created directories
        base_dir = os.path.join("crowdsourcing_ingestion_data", time.strftime("%Y_%m"))
        metadata_dir = os.path.join(base_dir, "metadata")
        citations_dir = os.path.join(base_dir, "citations")

        # Should have 2 files in each directory (1000 records in first file, 200 in second)
        self.assertEqual(len(os.listdir(metadata_dir)), 2)
        self.assertEqual(len(os.listdir(citations_dir)), 2)

        # Verify content of first metadata file (should have 1000 records)
        with open(os.path.join(metadata_dir, "0.csv"), "r") as f:
            metadata = list(csv.DictReader(f))
            self.assertEqual(len(metadata), 1000)

        # Verify content of second metadata file (should have 200 records)
        with open(os.path.join(metadata_dir, "1.csv"), "r") as f:
            metadata = list(csv.DictReader(f))
            self.assertEqual(len(metadata), 200)

        # Verify content of first citations file (should have 1000 records)
        with open(os.path.join(citations_dir, "0.csv"), "r") as f:
            citations = list(csv.DictReader(f))
            self.assertEqual(len(citations), 1000)

        # Verify content of second citations file (should have 200 records)
        with open(os.path.join(citations_dir, "1.csv"), "r") as f:
            citations = list(csv.DictReader(f))
            self.assertEqual(len(citations), 200)

    @patch("SPARQLWrapper.SPARQLWrapper.query")
    def test_check_triplestore_connection_success(self, mock_query):
        # Test successful connection
        result = check_triplestore_connection("http://example.com/sparql")
        self.assertTrue(result)
        mock_query.assert_called_once()

    @patch("SPARQLWrapper.SPARQLWrapper.query")
    def test_check_triplestore_connection_failure(self, mock_query):
        # Test failed connection
        mock_query.side_effect = Exception("Connection failed")
        result = check_triplestore_connection("http://example.com/sparql")
        self.assertFalse(result)
        mock_query.assert_called_once()

    @patch("meta_runner.run_meta_process")
    def test_process_single_issue_success(self, mock_run_meta):
        # Prepare test data
        issue = {
            "body": "id,title\n1,Test Title\n===###===@@@===citing,cited\n123,456",
            "number": "1",
        }
        base_settings = {
            "triplestore_url": "http://example.com/sparql",
            "base_output_dir": "/mnt/arcangelo/meta_output_current",
        }

        # Run the function
        success = process_single_issue(issue, base_settings)

        # Verify results
        self.assertTrue(success)
        mock_run_meta.assert_called_once()

        # Check that temporary config was created and then deleted
        base_dir = os.path.join("crowdsourcing_ingestion_data", time.strftime("%Y_%m"))
        temp_config_path = os.path.join(base_dir, "meta_config_1.yaml")
        self.assertFalse(os.path.exists(temp_config_path))

        # Verify metadata and citations were stored
        metadata_dir = os.path.join(base_dir, "metadata")
        citations_dir = os.path.join(base_dir, "citations")
        self.assertTrue(os.path.exists(metadata_dir))
        self.assertTrue(os.path.exists(citations_dir))
        self.assertEqual(len(os.listdir(metadata_dir)), 1)
        self.assertEqual(len(os.listdir(citations_dir)), 1)

    @patch("meta_runner.run_meta_process")
    def test_process_single_issue_meta_process_failure(self, mock_run_meta):
        # Prepare test data
        issue = {
            "body": "id,title\n1,Test Title\n===###===@@@===citing,cited\n123,456",
            "number": "1",
        }
        base_settings = {
            "triplestore_url": "http://example.com/sparql",
            "base_output_dir": "/mnt/arcangelo/meta_output_current",
        }

        # Make meta_process raise an exception
        mock_run_meta.side_effect = Exception("Meta process failed")

        # Run the function
        success = process_single_issue(issue, base_settings)

        # Verify results
        self.assertFalse(success)
        mock_run_meta.assert_called_once()

        # Check that temporary config was cleaned up
        base_dir = os.path.join("crowdsourcing_ingestion_data", time.strftime("%Y_%m"))
        temp_config_path = os.path.join(base_dir, "meta_config_1.yaml")
        self.assertFalse(os.path.exists(temp_config_path))

    def test_process_single_issue_invalid_issue(self):
        # Test with invalid issue data
        issue = {"body": "Invalid issue body without separator", "number": "1"}
        base_settings = {
            "triplestore_url": "http://example.com/sparql",
            "base_output_dir": "/mnt/arcangelo/meta_output_current",
        }

        # Run the function
        success = process_single_issue(issue, base_settings)

        # Verify results
        self.assertFalse(success)

        # Check that no files were created
        base_dir = os.path.join("crowdsourcing_ingestion_data", time.strftime("%Y_%m"))
        metadata_dir = os.path.join(base_dir, "metadata")
        citations_dir = os.path.join(base_dir, "citations")
        self.assertTrue(os.path.exists(metadata_dir))
        self.assertTrue(os.path.exists(citations_dir))
        self.assertEqual(len(os.listdir(metadata_dir)), 0)
        self.assertEqual(len(os.listdir(citations_dir)), 0)

    @patch("meta_runner.run_meta_process")
    def test_process_single_issue_settings_update(self, mock_run_meta):
        # Prepare test data
        issue = {
            "body": "id,title\n1,Test Title\n===###===@@@===citing,cited\n123,456",
            "number": "1",
        }
        base_settings = {
            "triplestore_url": "http://example.com/sparql",
            "base_output_dir": "/mnt/arcangelo/meta_output_current",
            "some_other_setting": "value",
        }

        # Run the function
        success = process_single_issue(issue, base_settings)

        # Verify results
        self.assertTrue(success)

        # Check that run_meta_process was called with correct settings
        called_settings = mock_run_meta.call_args[1]["settings"]
        self.assertEqual(
            called_settings["source"],
            f"https://github.com/{os.environ['GITHUB_REPOSITORY']}/issues/1",
        )
        self.assertEqual(called_settings["some_other_setting"], "value")
        self.assertTrue(called_settings["input_csv_dir"].endswith("metadata"))

    @patch("meta_runner.run_meta_process")
    def test_process_single_issue_general_exception(self, mock_run_meta):
        """Test handling of general exceptions in process_single_issue."""
        # Prepare test data
        issue = {
            "body": "id,title\n1,Test Title\n===###===@@@===citing,cited\n123,456",
            "number": "1",
        }
        base_settings = {
            "triplestore_url": "http://example.com/sparql",
            "base_output_dir": "/test/output",
        }

        # Make run_meta_process raise a general exception
        mock_run_meta.side_effect = Exception("Unexpected error")

        # Run the function
        success = process_single_issue(issue, base_settings)

        # Verify results
        self.assertFalse(success)
        mock_run_meta.assert_called_once()

        # Check that temporary config was cleaned up
        base_dir = os.path.join("crowdsourcing_ingestion_data", time.strftime("%Y_%m"))
        temp_config_path = os.path.join(base_dir, "meta_config_1.yaml")
        self.assertFalse(os.path.exists(temp_config_path))


class TestUpdateIssueLabels(unittest.TestCase):
    """Test the update_issue_labels function."""

    def setUp(self):
        """Set up test environment before each test."""
        self.issue_number = "123"
        self.env_patcher = patch.dict(
            "os.environ",
            {
                "GH_TOKEN": "fake-token",
                "GITHUB_REPOSITORY": "test/repo",
            },
        )
        self.env_patcher.start()
        self.base_url = (
            f"https://api.github.com/repos/test/repo/issues/{self.issue_number}"
        )
        self.headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer fake-token",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def tearDown(self):
        """Clean up after each test."""
        self.env_patcher.stop()

    @patch("requests.delete")
    @patch("requests.post")
    def test_successful_update_on_success(self, mock_post, mock_delete):
        """Test successful label update when processing succeeds."""
        # Setup mocks
        mock_delete.return_value.status_code = 200
        mock_post.return_value.status_code = 201

        # Call function
        update_issue_labels(self.issue_number, success=True)

        # Verify delete call to remove 'to be processed'
        mock_delete.assert_called_once_with(
            f"{self.base_url}/labels/to%20be%20processed",
            headers=self.headers,
            timeout=30,
        )

        # Verify post call to add 'done' label
        mock_post.assert_called_once_with(
            f"{self.base_url}/labels",
            headers=self.headers,
            json={"labels": ["done"]},
            timeout=30,
        )

    @patch("requests.delete")
    @patch("requests.post")
    def test_successful_update_on_failure(self, mock_post, mock_delete):
        """Test successful label update when processing fails."""
        # Setup mocks
        mock_delete.return_value.status_code = 200
        mock_post.return_value.status_code = 201

        # Call function
        update_issue_labels(self.issue_number, success=False)

        # Verify delete call to remove 'to be processed'
        mock_delete.assert_called_once_with(
            f"{self.base_url}/labels/to%20be%20processed",
            headers=self.headers,
            timeout=30,
        )

        # Verify post call to add 'oc meta error' label
        mock_post.assert_called_once_with(
            f"{self.base_url}/labels",
            headers=self.headers,
            json={"labels": ["oc meta error"]},
            timeout=30,
        )

    @patch("requests.delete")
    def test_delete_label_error(self, mock_delete):
        """Test error handling when removing label fails."""
        # Setup mock to raise exception
        mock_delete.side_effect = requests.RequestException("Network error")

        # Verify exception is raised
        with self.assertRaises(requests.RequestException) as context:
            update_issue_labels(self.issue_number, success=True)

        self.assertEqual(str(context.exception), "Network error")
        mock_delete.assert_called_once()

    @patch("requests.delete")
    @patch("requests.post")
    def test_add_label_error(self, mock_post, mock_delete):
        """Test error handling when adding new label fails."""
        # Setup mocks
        mock_delete.return_value.status_code = 200
        mock_post.side_effect = requests.RequestException("Network error")

        # Verify exception is raised
        with self.assertRaises(requests.RequestException) as context:
            update_issue_labels(self.issue_number, success=True)

        self.assertEqual(str(context.exception), "Network error")
        mock_delete.assert_called_once()
        mock_post.assert_called_once()


class TestProcessMetaIssues(unittest.TestCase):
    """Test the main process_meta_issues function."""

    def setUp(self):
        """Set up test environment."""
        self.env_patcher = patch.dict(
            "os.environ",
            {
                "GH_TOKEN": "fake-token",
                "GITHUB_REPOSITORY": "test/repo",
            },
        )
        self.env_patcher.start()

        # Setup test configuration
        self.config_content = {
            "triplestore_url": "http://example.com/sparql",
            "base_output_dir": "/test/output",
        }

        # Patch yaml.safe_load to return our test config
        self.yaml_patcher = patch("yaml.safe_load")
        self.mock_yaml_load = self.yaml_patcher.start()
        self.mock_yaml_load.return_value = self.config_content

    def tearDown(self):
        """Clean up after each test."""
        self.env_patcher.stop()
        self.yaml_patcher.stop()

    @patch("meta_runner.check_triplestore_connection")
    @patch("meta_runner.get_closed_issues")
    @patch("meta_runner.process_single_issue")
    @patch("meta_runner.update_issue_labels")
    def test_successful_processing(
        self, mock_update_labels, mock_process_issue, mock_get_issues, mock_check_conn
    ):
        """Test successful processing of multiple issues."""
        # Setup mocks
        mock_check_conn.return_value = True
        mock_get_issues.return_value = [
            {"body": "test1", "number": "1"},
            {"body": "test2", "number": "2"},
        ]
        mock_process_issue.return_value = True

        # Run function
        process_meta_issues()

        # Verify all issues were processed
        self.assertEqual(mock_process_issue.call_count, 2)
        self.assertEqual(mock_update_labels.call_count, 2)

        # Verify correct parameters were passed
        mock_process_issue.assert_any_call(
            {"body": "test1", "number": "1"}, self.config_content
        )
        mock_update_labels.assert_any_call("1", True)
        mock_process_issue.assert_any_call(
            {"body": "test2", "number": "2"}, self.config_content
        )
        mock_update_labels.assert_any_call("2", True)

    @patch("meta_runner.check_triplestore_connection")
    def test_triplestore_not_responsive(self, mock_check_conn):
        """Test behavior when triplestore is not responsive."""
        mock_check_conn.return_value = False

        # Run function
        process_meta_issues()

        # Verify early return
        mock_check_conn.assert_called_once_with(self.config_content["triplestore_url"])

    @patch("meta_runner.check_triplestore_connection")
    @patch("meta_runner.get_closed_issues")
    def test_no_issues_to_process(self, mock_get_issues, mock_check_conn):
        """Test behavior when no issues are found."""
        mock_check_conn.return_value = True
        mock_get_issues.return_value = []

        # Run function
        process_meta_issues()

        # Verify early return after finding no issues
        mock_get_issues.assert_called_once()

    @patch("meta_runner.check_triplestore_connection")
    @patch("meta_runner.get_closed_issues")
    @patch("meta_runner.process_single_issue")
    @patch("meta_runner.update_issue_labels")
    def test_mixed_processing_results(
        self, mock_update_labels, mock_process_issue, mock_get_issues, mock_check_conn
    ):
        """Test processing with both successful and failed issues."""
        # Setup mocks
        mock_check_conn.return_value = True
        mock_get_issues.return_value = [
            {"body": "test1", "number": "1"},
            {"body": "test2", "number": "2"},
        ]
        # First issue succeeds, second fails
        mock_process_issue.side_effect = [True, False]

        # Run function
        process_meta_issues()

        # Verify all issues were processed
        self.assertEqual(mock_process_issue.call_count, 2)
        self.assertEqual(mock_update_labels.call_count, 2)

        # Verify correct labels were set
        mock_update_labels.assert_any_call("1", True)
        mock_update_labels.assert_any_call("2", False)

    @patch("meta_runner.check_triplestore_connection")
    @patch("meta_runner.get_closed_issues")
    @patch("meta_runner.process_single_issue")
    @patch("meta_runner.update_issue_labels")
    def test_error_handling(
        self, mock_update_labels, mock_process_issue, mock_get_issues, mock_check_conn
    ):
        """Test error handling during processing."""
        # Setup mocks
        mock_check_conn.return_value = True
        mock_get_issues.return_value = [{"body": "test1", "number": "1"}]
        mock_process_issue.side_effect = Exception("Processing error")

        # Verify exception is propagated
        with self.assertRaises(Exception) as context:
            process_meta_issues()

        self.assertEqual(str(context.exception), "Processing error")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
