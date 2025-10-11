#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2022, Arcangelo Massari <arcangelo.massari@unibo.it>
#
# Permission to use, copy, modify, and/or distribute this software for any purpose
# with or without fee is hereby granted, provided that the above copyright notice
# and this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
# REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND
# FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT, INDIRECT,
# OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS OF USE,
# DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS
# ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS
# SOFTWARE.

import json
import os
import shutil
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

import requests
import yaml
from dotenv import load_dotenv
from crowdsourcing.process_issues import (
    _create_deposition_resource,
    _get_zenodo_token,
    _upload_data,
    _validate_title,
    answer,
    deposit_on_zenodo,
    get_data_to_store,
    get_open_issues,
    get_user_id,
    is_in_safe_list,
    process_open_issues,
    validate,
)
from requests.exceptions import RequestException

load_dotenv()  # Carica le variabili dal file .env


class TestTitleValidation(unittest.TestCase):
    def test_valid_doi_title(self):
        """Test that a valid DOI title is accepted"""
        title = "deposit journal.com doi:10.1007/s42835-022-01029-y"
        is_valid, message = _validate_title(title)
        self.assertTrue(is_valid)
        self.assertEqual(message, "")

    def test_valid_isbn_title(self):
        """Test that a valid ISBN title is accepted"""
        title = "deposit publisher.com isbn:9780134093413"
        is_valid, message = _validate_title(title)
        self.assertTrue(is_valid)
        self.assertEqual(message, "")

    def test_missing_deposit_keyword(self):
        """Test that title without 'deposit' keyword is rejected"""
        title = "submit journal.com doi:10.1007/s42835-022-01029-y"
        is_valid, message = _validate_title(title)
        self.assertFalse(is_valid)
        self.assertIn("title of the issue was not structured correctly", message)

    def test_unsupported_identifier(self):
        """Test that unsupported identifier types are rejected"""
        title = "deposit journal.com arxiv:2203.01234"
        is_valid, message = _validate_title(title)
        self.assertFalse(is_valid)
        self.assertEqual(message, "The identifier schema 'arxiv' is not supported")

    def test_invalid_doi(self):
        """Test that invalid DOI format is rejected"""
        title = "deposit journal.com doi:invalid-doi-format"
        is_valid, message = _validate_title(title)
        self.assertFalse(is_valid)
        self.assertIn("is not a valid DOI", message)

    def test_malformed_title(self):
        """Test that malformed title structure is rejected"""
        title = "deposit doi:10.1007/s42835-022-01029-y"  # missing domain
        is_valid, message = _validate_title(title)
        self.assertFalse(is_valid)
        self.assertIn("title of the issue was not structured correctly", message)

    def test_unsupported_schema(self):
        """Test that an unsupported identifier schema returns appropriate error"""
        title = "deposit journal.com issn:1234-5678"  # issn is not in supported schemas
        is_valid, message = _validate_title(title)
        self.assertFalse(is_valid)
        print("message", message)
        self.assertEqual(message, "The identifier schema 'issn' is not supported")

    def test_valid_temp_id_title(self):
        """Test that a valid temporary ID title is accepted"""
        title = "deposit journal.com temp:12345"
        is_valid, message = _validate_title(title)
        self.assertTrue(is_valid)
        self.assertEqual(message, "")

    def test_valid_local_id_title(self):
        """Test that a valid local ID title is accepted"""
        title = "deposit journal.com local:record123"
        is_valid, message = _validate_title(title)
        self.assertTrue(is_valid)
        self.assertEqual(message, "")

    def test_invalid_temp_id_format(self):
        """Test that invalid temporary ID format is rejected"""
        title = "deposit journal.com temp12345"  # Missing colon
        is_valid, message = _validate_title(title)
        self.assertFalse(is_valid)
        self.assertIn("title of the issue was not structured correctly", message)

    def test_invalid_local_id_format(self):
        """Test that invalid local ID format is rejected"""
        title = "deposit journal.com local.record123"  # Wrong separator
        is_valid, message = _validate_title(title)
        self.assertFalse(is_valid)
        self.assertIn("title of the issue was not structured correctly", message)


class TestValidation(unittest.TestCase):
    def setUp(self):
        """Set up test environment before each test"""
        # Create temporary test directory
        self.test_dir = os.path.join(os.path.dirname(__file__), "temp_test_dir")
        self.validation_output = os.path.join(self.test_dir, "validation_output")
        self.validation_reports = os.path.join(self.test_dir, "validation_reports")

        os.makedirs(self.validation_output, exist_ok=True)
        os.makedirs(self.validation_reports, exist_ok=True)

        # Setup environment variables
        self.env_patcher = patch.dict(
            "os.environ",
            {"GH_TOKEN": "fake-token", "GITHUB_REPOSITORY": "test-org/test-repo"},
        )
        self.env_patcher.start()

    def tearDown(self):
        """Clean up after each test"""
        # Stop environment patcher
        self.env_patcher.stop()

        # Clean up test directory
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_valid_issue(self):
        """Test that a valid issue with correct title and CSV data is accepted"""
        title = "deposit journal.com doi:10.1007/s42835-022-01029-y"
        body = """"id","title","author","pub_date","venue","volume","issue","page","type","publisher","editor"
"doi:10.1007/s42835-022-01029-y","A Study on Electric Properties","Smith, John","2024","Journal of Physics","5","2","100-120","journal article","Test Publisher",""
"doi:10.1007/978-3-662-07918-8_3","Influence of Dielectric Properties, State, and Electrodes on Electric Strength","Ushakov, Vasily Y.","2004","Insulation of High-Voltage Equipment [isbn:9783642058530 isbn:9783662079188]","","","27-82","book chapter","Springer Science and Business Media LLC [crossref:297]",""
"doi:10.1016/0021-9991(73)90147-2","Flux-corrected transport. I. SHASTA, a fluid transport algorithm that works","Boris, Jay P; Book, David L","1973-01","Journal of Computational Physics [issn:0021-9991]","11","1","38-69","journal article","Elsevier BV [crossref:78]",""
===###===@@@===
"citing_id","cited_id"
"doi:10.1007/s42835-022-01029-y","doi:10.1007/978-3-662-07918-8_3"
"doi:10.1007/s42835-022-01029-y","doi:10.1016/0021-9991(73)90147-2\""""
        is_valid, message = validate(
            title,
            body,
            "123",
            validation_output_dir=self.validation_output,
            validation_reports_dir=self.validation_reports,
        )
        self.assertTrue(is_valid)
        self.assertIn("Thank you for your contribution", message)

    def test_invalid_separator(self):
        """Test that issue with incorrect separator is rejected"""
        title = "deposit journal.com doi:10.1007/s42835-022-01029-y"
        body = """"id","title","author","pub_date","venue","volume","issue","page","type","publisher","editor"
"doi:10.1007/978-3-662-07918-8_3","Test Title","Test Author","2004","Test Venue","1","1","1-10","journal article","Test Publisher",""
WRONG_SEPARATOR
"citing_id","cited_id"
"doi:10.1007/s42835-022-01029-y","doi:10.1007/978-3-662-07918-8_3\""""
        is_valid, message = validate(
            title,
            body,
            "124",
            validation_output_dir=self.validation_output,
            validation_reports_dir=self.validation_reports,
        )
        self.assertFalse(is_valid)
        self.assertIn("Please use the separator", message)

    def test_invalid_title_valid_body(self):
        """Test that issue with invalid title but valid body is rejected"""
        title = "invalid title format"
        body = """"id","title","author","pub_date","venue","volume","issue","page","type","publisher","editor"
"doi:10.1007/978-3-662-07918-8_3","Test Title","Test Author","2004","Test Venue","1","1","1-10","journal article","Test Publisher",""
===###===@@@===
"citing_id","cited_id"
"doi:10.1007/s42835-022-01029-y","doi:10.1007/978-3-662-07918-8_3\""""
        is_valid, message = validate(
            title,
            body,
            "125",
            validation_output_dir=self.validation_output,
            validation_reports_dir=self.validation_reports,
        )
        self.assertFalse(is_valid)
        self.assertIn("title of the issue was not structured correctly", message)

    def test_invalid_csv_structure(self):
        """Test that CSV with wrong column structure returns appropriate error"""
        title = "deposit journal.com doi:10.1007/s42835-022-01029-y"
        body = """"wrong","column","headers"
"data1","data2","data3"
===###===@@@===
"wrong","citation","headers"
"cite1","cite2","cite3"\""""
        is_valid, message = validate(
            title,
            body,
            "126",
            validation_output_dir=self.validation_output,
            validation_reports_dir=self.validation_reports,
        )
        self.assertFalse(is_valid)
        self.assertIn(
            "Please ensure both metadata and citations are valid CSVs following the required format.",
            message,
        )

    def test_get_data_to_store_valid_input(self):
        """Test get_data_to_store with valid input data"""
        title = "deposit journal.com doi:10.1234/test"
        body = """"id","title"
"1","Test Title"
===###===@@@===
"citing","cited"
"id1","id2"\""""
        created_at = "2024-01-01T00:00:00Z"
        had_primary_source = "https://github.com/test/1"
        user_id = 12345

        result = get_data_to_store(title, body, created_at, had_primary_source, user_id)

        self.assertEqual(result["data"]["title"], title)
        self.assertEqual(len(result["data"]["metadata"]), 1)
        self.assertEqual(len(result["data"]["citations"]), 1)
        self.assertEqual(result["provenance"]["generatedAtTime"], created_at)
        self.assertEqual(
            result["provenance"]["wasAttributedTo"],
            f"https://api.github.com/user/{user_id}",
        )
        self.assertEqual(result["provenance"]["hadPrimarySource"], had_primary_source)

    def test_get_data_to_store_invalid_csv(self):
        """Test get_data_to_store with invalid CSV format"""
        title = "deposit journal.com doi:10.1234/test"
        # CSV con una sola sezione (manca il separatore)
        body = """"id","title"
"1","Test Title"\""""

        with self.assertRaises(ValueError) as context:
            get_data_to_store(
                title, body, "2024-01-01T00:00:00Z", "https://github.com/test/1", 12345
            )

        # Verifichiamo che l'errore contenga il messaggio corretto
        self.assertIn("Failed to process issue data", str(context.exception))

    def test_get_data_to_store_empty_sections(self):
        """Test get_data_to_store with empty metadata or citations sections"""
        title = "deposit journal.com doi:10.1234/test"
        body = """"id","title"
===###===@@@===
"citing","cited"\""""

        with self.assertRaises(ValueError) as context:
            get_data_to_store(
                title, body, "2024-01-01T00:00:00Z", "https://github.com/test/1", 12345
            )

        self.assertIn("Empty metadata or citations section", str(context.exception))

    def test_get_data_to_store_invalid_separator(self):
        """Test get_data_to_store with invalid separator in body"""
        title = "deposit journal.com doi:10.1234/test"
        body = """"id","title"
INVALID_SEPARATOR
"citing","cited"\""""

        with self.assertRaises(ValueError) as context:
            get_data_to_store(
                title, body, "2024-01-01T00:00:00Z", "https://github.com/test/1", 12345
            )

        self.assertIn("Failed to process issue data", str(context.exception))

    @patch("crowdsourcing.process_issues.get_open_issues")
    @patch("crowdsourcing.process_issues.get_user_id")
    @patch("crowdsourcing.process_issues.is_in_safe_list")
    @patch("crowdsourcing.process_issues.validate")
    @patch("crowdsourcing.process_issues.get_data_to_store")
    @patch("crowdsourcing.process_issues.answer")
    @patch("crowdsourcing.process_issues.deposit_on_zenodo")
    @patch("crowdsourcing.process_issues.archive_manager")
    def test_validation_with_validator(self, mock_archive_manager, *args):
        """Test validation using the oc_validator library"""
        title = "deposit journal.com doi:10.1007/s42835-022-01029-y"
        # CSV con errori di validazione intenzionali
        body = """"id","title","author","pub_date","venue","volume","issue","page","type","publisher","editor"
"doi:10.1007/s42835-022-01029-y","","","","","","","","invalid_type","",""
===###===@@@===
"citing_id","cited_id"
"doi:10.1007/s42835-022-01029-y","invalid_doi\""""

        # Run validation
        is_valid, message = validate(
            title,
            body,
            "127",
            validation_output_dir=self.validation_output,
            validation_reports_dir=self.validation_reports,
        )

        # Verify validation failed
        self.assertFalse(is_valid)
        self.assertIn("Validation errors found in", message)
        self.assertIn("metadata and citations", message)

        # Verify final report was generated in validation_reports
        report_files = os.listdir(self.validation_reports)
        self.assertTrue(
            any(
                f.startswith("validation_") and f.endswith(".html")
                for f in report_files
            )
        )

        # Verify archive_manager.add_report was called
        mock_archive_manager.add_report.assert_called_once()

    def test_validation_with_metadata_validation_file(self):
        """Test validation when metadata validation file contains errors"""
        title = "deposit journal.com doi:10.1007/s42835-022-01029-y"
        # Invalid metadata CSV with missing required fields
        body = """"wrong_field","another_wrong"
"value1","value2"
===###===@@@===
"citing_id","cited_id"
"doi:10.1007/s42835-022-01029-y","doi:10.1007/978-3-030-00668-6_8\""""

        is_valid, message = validate(
            title,
            body,
            "128",
            validation_output_dir=self.validation_output,
            validation_reports_dir=self.validation_reports,
        )

        self.assertFalse(is_valid)
        self.assertIn(
            "Please ensure both metadata and citations are valid CSVs", message
        )
        self.assertIn("check our guide", message)

    def test_validation_with_both_validation_files(self):
        """Test validation when both metadata and citations have validation errors"""
        title = "deposit journal.com doi:10.1007/s42835-022-01029-y"
        # Invalid metadata missing fields and invalid citation identifiers
        body = """"id","title"
"doi:invalid","Test Title"
===###===@@@===
"citing_id","cited_id"
"invalid:123","another:456"\""""

        is_valid, message = validate(
            title,
            body,
            "129",
            validation_output_dir=self.validation_output,
            validation_reports_dir=self.validation_reports,
        )

        self.assertFalse(is_valid)
        self.assertIn(
            "Please ensure both metadata and citations are valid CSVs", message
        )
        self.assertIn("check our guide", message)

    @patch("crowdsourcing.process_issues.archive_manager")
    def test_validation_reads_validation_files(self, mock_archive_manager):
        """Test that validation properly reads and processes validation files"""
        title = "deposit journal.com doi:10.1007/s42835-022-01029-y"
        # CSV con errori di validazione intenzionali
        body = """"id","title","author","pub_date","venue","volume","issue","page","type","publisher","editor"
"doi:10.1007/s42835-022-01029-y","","","","","","","","invalid_type","",""
"doi:10.1162/qss_a_00292","","","","","","","","journal article","",""
===###===@@@===
"citing_id","cited_id"
"doi:10.1007/s42835-022-01029-y","invalid_doi"
"doi:10.1162/qss_a_00292","doi:10.1007/s42835-022-01029-y"\""""

        # Run validation
        is_valid, message = validate(
            title,
            body,
            "130",
            validation_output_dir=self.validation_output,
            validation_reports_dir=self.validation_reports,
        )

        # Verify validation failed
        self.assertFalse(is_valid)
        self.assertIn("Validation errors found in metadata and citations", message)
        self.assertIn("Please check the detailed validation report:", message)
        self.assertIn(
            "test-org.github.io/test-repo/validation_reports/index.html?report=validation_",
            message,
        )
        self.assertIn(".html", message)

        # Verify final report was generated in validation_reports
        report_files = os.listdir(self.validation_reports)
        self.assertTrue(
            any(
                f.startswith("validation_") and f.endswith(".html")
                for f in report_files
            )
        )

        # Verify archive_manager.add_report was called
        mock_archive_manager.add_report.assert_called_once()

    @patch("crowdsourcing.process_issues.archive_manager")
    def test_validation_html_report_generation(self, mock_archive_manager):
        """Test that HTML validation reports are properly generated when validation fails"""
        # Clean up any existing directories from previous tests
        title = "deposit journal.com doi:10.1007/s42835-022-01029-y"
        # Invalid data that will fail validation
        body = """"id","title","author","pub_date","venue","volume","issue","page","type","publisher","editor"
"INVALID_DOI","Test Title","Test Author","2024","Test Journal","1","1","1-10","journal article","Test Publisher",""
===###===@@@===
"citing_id","cited_id"
"INVALID_DOI","doi:10.1007/978-3-030-00668-6_8\""""

        # Run validation
        is_valid, message = validate(
            title,
            body,
            "131",
            validation_output_dir=self.validation_output,
            validation_reports_dir=self.validation_reports,
        )

        # Verify validation failed
        self.assertFalse(is_valid)

        # Check that merged report exists in validation_reports
        report_files = os.listdir(self.validation_reports)
        self.assertTrue(
            any(
                f.startswith("validation_") and f.endswith(".html")
                for f in report_files
            )
        )

        # Verify report URL is in the error message
        self.assertIn("Please check the detailed validation report:", message)
        self.assertIn(
            "test-org.github.io/test-repo/validation_reports/index.html?report=validation_",
            message,
        )
        self.assertIn(".html", message)

    @patch("crowdsourcing.process_issues.archive_manager")
    def test_validation_html_report_generation_only_metadata_errors(
        self, mock_archive_manager
    ):
        """Test HTML report generation when only metadata has validation errors"""
        title = "deposit journal.com doi:10.1007/s42835-022-01029-y"
        # CSV with invalid metadata but valid citations
        body = """"id","title","author","pub_date","venue","volume","issue","page","type","publisher","editor"
"doi:10.1007/s42835-022-01029-y","Test Title","","","","","","","invalid_type","",""
"doi:10.1162/qss_a_00292","Test Title","","","","","","","journal article","",""
===###===@@@===
"citing_id","cited_id"
"doi:10.1007/s42835-022-01029-y","doi:10.1162/qss_a_00292\""""

        # Run validation
        is_valid, message = validate(
            title,
            body,
            "132",
            validation_output_dir=self.validation_output,
            validation_reports_dir=self.validation_reports,
        )

        # Verify validation failed
        self.assertFalse(is_valid)

        # Check that final report exists
        report_files = [
            f for f in os.listdir(self.validation_reports) if f.endswith(".html")
        ]
        self.assertEqual(len(report_files), 1, "Should be exactly one final report")
        final_report = report_files[0]
        self.assertTrue(final_report.startswith("validation_"))

        # Verify archive_manager.add_report was called with correct parameters
        mock_archive_manager.add_report.assert_called_once_with(
            final_report,
            f"https://test-org.github.io/test-repo/validation_reports/{final_report}",
        )

    @patch("crowdsourcing.process_issues.archive_manager")
    def test_validation_html_report_generation_only_citations_errors(
        self, mock_archive_manager
    ):
        """Test HTML report generation when only citations have validation errors"""
        title = "deposit journal.com doi:10.1007/s42835-022-01029-y"
        # CSV with valid metadata but invalid citations
        body = """"id","title","author","pub_date","venue","volume","issue","page","type","publisher","editor"
"doi:10.1007/s42835-022-01029-y","Test Title","Test Author","2024","Test Journal","1","1","1-10","journal article","Test Publisher",""
===###===@@@===
"citing_id","cited_id"
"INVALID_DOI","ANOTHER_INVALID_DOI"\""""

        # Run validation
        is_valid, message = validate(
            title,
            body,
            "133",
            validation_output_dir=self.validation_output,
            validation_reports_dir=self.validation_reports,
        )

        # Verify validation failed
        self.assertFalse(is_valid)

        # Check that final report exists
        report_files = [
            f for f in os.listdir(self.validation_reports) if f.endswith(".html")
        ]
        self.assertEqual(len(report_files), 1, "Should be exactly one final report")
        final_report = report_files[0]
        self.assertTrue(final_report.startswith("validation_"))

        # Verify archive_manager.add_report was called with correct parameters
        mock_archive_manager.add_report.assert_called_once_with(
            final_report,
            f"https://test-org.github.io/test-repo/validation_reports/{final_report}",
        )

    def test_validate_empty_body(self):
        """Test validate() with empty body content"""
        title = "deposit journal.com doi:10.1162/qss_a_00292"
        body = None

        is_valid, message = validate(
            title,
            body,
            "134",
            validation_output_dir=self.validation_output,
            validation_reports_dir=self.validation_reports,
        )

        self.assertFalse(is_valid)
        self.assertIn("The issue body cannot be empty", message)
        self.assertIn(
            "https://github.com/opencitations/crowdsourcing/blob/main/README.md",
            message,
        )

    def test_validate_empty_string_body(self):
        """Test validate() with empty string body content"""
        title = "deposit journal.com doi:10.1162/qss_a_00292"
        body = ""

        is_valid, message = validate(
            title,
            body,
            "135",
            validation_output_dir=self.validation_output,
            validation_reports_dir=self.validation_reports,
        )

        self.assertFalse(is_valid)
        self.assertIn("The issue body cannot be empty", message)
        self.assertIn(
            "https://github.com/opencitations/crowdsourcing/blob/main/README.md",
            message,
        )

    def test_validation_report_issue_number(self):
        """Test that validation report filename contains correct issue number"""
        title = "deposit journal.com doi:10.1007/s42835-022-01029-y"
        body = """"id","title","author","pub_date","venue","volume","issue","page","type","publisher","editor"
"doi:10.1007/s42835-022-01029-y","","","","","","","","invalid_type","",""
===###===@@@===
"citing_id","cited_id"
"doi:10.1007/s42835-022-01029-y","invalid_doi"\""""

        test_issue_number = "42"

        # Run validation
        is_valid, message = validate(
            title,
            body,
            test_issue_number,
            validation_output_dir=self.validation_output,
            validation_reports_dir=self.validation_reports,
        )

        # Verify validation failed and generated a report
        self.assertFalse(is_valid)

        # Check that the report file exists with correct issue number
        report_files = os.listdir(self.validation_reports)
        matching_files = [
            f
            for f in report_files
            if f.startswith(f"validation_issue_{test_issue_number}")
        ]
        self.assertEqual(
            len(matching_files), 1, "Should find exactly one matching report file"
        )
        self.assertTrue(
            matching_files[0].endswith(".html"), "Report file should be HTML"
        )
        self.assertEqual(
            matching_files[0], f"validation_issue_{test_issue_number}.html"
        )

    def test_valid_temp_ids_in_csv(self):
        """Test that CSV data with temporary IDs is accepted"""
        title = "deposit journal.com doi:10.1007/s42835-022-01029-y"
        body = """"id","title","author","pub_date","venue","volume","issue","page","type","publisher","editor"
"temp:123","Test Title","Test Author","2024","Test Journal","1","1","1-10","journal article","Test Publisher",""
"temp:456","Another Title","Another Author","2024","Test Journal","1","1","11-20","journal article","Test Publisher",""
===###===@@@===
"citing_id","cited_id"
"temp:123","temp:456\""""
        is_valid, message = validate(
            title,
            body,
            "136",
            validation_output_dir=self.validation_output,
            validation_reports_dir=self.validation_reports,
        )
        self.assertTrue(is_valid)
        self.assertIn("Thank you for your contribution", message)

    def test_valid_local_ids_in_csv(self):
        """Test that CSV data with local IDs is accepted"""
        title = "deposit journal.com doi:10.1007/s42835-022-01029-y"
        body = """"id","title","author","pub_date","venue","volume","issue","page","type","publisher","editor"
"local:rec1","Test Title","Test Author","2024","Test Journal","1","1","1-10","journal article","Test Publisher",""
"local:rec2","Another Title","Another Author","2024","Test Journal","1","1","11-20","journal article","Test Publisher",""
===###===@@@===
"citing_id","cited_id"
"local:rec1","local:rec2\""""
        is_valid, message = validate(
            title,
            body,
            "137",
            validation_output_dir=self.validation_output,
            validation_reports_dir=self.validation_reports,
        )
        self.assertTrue(is_valid)
        self.assertIn("Thank you for your contribution", message)

    def test_mixed_identifier_types_in_csv(self):
        """Test that CSV data with mixed identifier types (DOI, temp, local) is accepted"""
        title = "deposit journal.com doi:10.1007/s42835-022-01029-y"
        body = """"id","title","author","pub_date","venue","volume","issue","page","type","publisher","editor"
"doi:10.1007/s42835-022-01029-y","Test Title","Test Author","2024","Test Journal","1","1","1-10","journal article","Test Publisher",""
"temp:123","Another Title","Another Author","2024","Test Journal","1","1","11-20","journal article","Test Publisher",""
"local:rec1","Third Title","Third Author","2024","Test Journal","1","1","21-30","journal article","Test Publisher",""
===###===@@@===
"citing_id","cited_id"
"doi:10.1007/s42835-022-01029-y","temp:123"
"temp:123","local:rec1\""""
        is_valid, message = validate(
            title,
            body,
            "138",
            validation_output_dir=self.validation_output,
            validation_reports_dir=self.validation_reports,
        )
        self.assertTrue(is_valid)
        self.assertIn("Thank you for your contribution", message)


class TestUserValidation(unittest.TestCase):
    def setUp(self):
        """Set up test environment before each test"""
        # Create a temporary test safe list file
        self.test_safe_list_path = "test_safe_list.yaml"
        test_safe_list = {
            "users": [
                {"id": 3869247, "name": "Silvio Peroni"},
                {"id": 42008604, "name": "Arcangelo Massari"},
            ]
        }
        with open(self.test_safe_list_path, "w") as f:
            yaml.dump(test_safe_list, f)

        # Create patcher to use test file instead of real one
        self.safe_list_patcher = patch(
            "crowdsourcing.process_issues.SAFE_LIST_PATH", self.test_safe_list_path
        )
        self.safe_list_patcher.start()

    def tearDown(self):
        """Clean up after each test"""
        # Remove temporary file
        if os.path.exists(self.test_safe_list_path):
            os.remove(self.test_safe_list_path)

        # Stop patcher
        self.safe_list_patcher.stop()

    def test_get_user_id_real_user(self):
        """Test getting ID of a real GitHub user"""
        with patch.dict("os.environ", {"GH_TOKEN": "fake-token"}):
            with patch("requests.get") as mock_get:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"id": 42008604}
                mock_get.return_value = mock_response

                user_id = get_user_id("arcangelo7")
                self.assertEqual(user_id, 42008604)

    def test_get_user_id_nonexistent_user(self):
        """Test getting ID of a nonexistent GitHub user"""
        with patch.dict("os.environ", {"GH_TOKEN": "fake-token"}):
            with patch("requests.get") as mock_get:
                mock_response = MagicMock()
                mock_response.status_code = 404
                mock_get.return_value = mock_response

                user_id = get_user_id("this_user_definitely_does_not_exist_123456789")
                self.assertIsNone(user_id)

    def test_is_in_safe_list_authorized(self):
        """Test that authorized user is in safe list"""
        self.assertTrue(is_in_safe_list(42008604))

    def test_is_in_safe_list_unauthorized(self):
        """Test that unauthorized user is not in safe list"""
        self.assertFalse(is_in_safe_list(99999999))

    def test_is_in_safe_list_file_not_found(self):
        """Test behavior when safe_list.yaml doesn't exist"""
        # Remove the test file to simulate missing file
        if os.path.exists(self.test_safe_list_path):
            os.remove(self.test_safe_list_path)

        # Test with any user ID - should return False when file is missing
        result = is_in_safe_list(42008604)

        # Verify result is False
        self.assertFalse(result)

        # Verify empty file was created with proper structure
        self.assertTrue(os.path.exists(self.test_safe_list_path))
        with open(self.test_safe_list_path, "r") as f:
            content = yaml.safe_load(f)
            self.assertEqual(content, {"users": []})

    def test_is_in_safe_list_invalid_yaml(self):
        """Test behavior with invalid YAML file"""
        with open(self.test_safe_list_path, "w") as f:
            f.write("invalid: yaml: content: [")
        self.assertFalse(is_in_safe_list(42008604))

    @patch("requests.get")
    @patch("time.sleep")
    @patch("time.time")
    def test_get_user_id_rate_limit(self, mock_time, mock_sleep, mock_get):
        """Test rate limit handling in get_user_id"""
        # Mock current time
        current_time = 1000000
        mock_time.return_value = current_time

        # Setup responses
        rate_limited_response = MagicMock()
        rate_limited_response.status_code = 403
        rate_limited_response.headers = {
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(current_time + 30),  # Reset in 30 seconds
        }

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {"id": 12345}

        # First call hits rate limit, second call succeeds
        mock_get.side_effect = [rate_limited_response, success_response]

        with patch.dict("os.environ", {"GH_TOKEN": "fake-token"}):
            user_id = get_user_id("test-user")

        # Verify correct user ID was returned
        self.assertEqual(user_id, 12345)

        # Verify sleep was called with correct duration
        mock_sleep.assert_called_once_with(30)

        # Verify correct number of API calls
        self.assertEqual(mock_get.call_count, 2)

        # Verify API calls were correct
        for call in mock_get.call_args_list:
            args, kwargs = call
            self.assertEqual(args[0], "https://api.github.com/users/test-user")
            self.assertEqual(kwargs["headers"]["Authorization"], "Bearer fake-token")

    @patch("requests.get")
    @patch("time.sleep")  # Mock sleep to speed up test
    def test_get_user_id_connection_error_retry(self, mock_sleep, mock_get):
        """Test retry behavior when connection errors occur"""
        # Configure mock to fail with connection error twice then succeed
        mock_get.side_effect = [
            requests.ConnectionError,
            requests.ConnectionError,
            MagicMock(status_code=200, json=lambda: {"id": 12345}),
        ]

        with patch.dict("os.environ", {"GH_TOKEN": "fake-token"}):
            user_id = get_user_id("test-user")

            self.assertEqual(user_id, 12345)
            self.assertEqual(mock_get.call_count, 3)
            self.assertEqual(mock_sleep.call_count, 2)
            mock_sleep.assert_called_with(5)  # Verify sleep duration

    @patch("requests.get")
    @patch("time.sleep")
    def test_get_user_id_all_retries_fail(self, mock_sleep, mock_get):
        """Test behavior when all retry attempts fail"""
        # Configure mock to fail all three attempts
        mock_get.side_effect = [
            requests.ConnectionError,
            requests.ConnectionError,
            requests.ConnectionError,
        ]

        with patch.dict("os.environ", {"GH_TOKEN": "fake-token"}):
            user_id = get_user_id("test-user")

            self.assertIsNone(user_id)
            self.assertEqual(mock_get.call_count, 3)
            self.assertEqual(
                mock_sleep.call_count, 3
            )  # Updated to expect 3 sleeps - one for each ConnectionError

    @patch("requests.get")
    @patch("time.sleep")
    def test_get_user_id_timeout_retry(self, mock_sleep, mock_get):
        """Test retry behavior when requests timeout"""
        # Configure mock to timeout twice then succeed
        mock_get.side_effect = [
            requests.ReadTimeout,
            requests.ReadTimeout,
            MagicMock(status_code=200, json=lambda: {"id": 12345}),
        ]

        with patch.dict("os.environ", {"GH_TOKEN": "fake-token"}):
            user_id = get_user_id("test-user")

        # Verify correct user ID was returned after retries
        self.assertEqual(user_id, 12345)

        # Verify correct number of attempts
        self.assertEqual(mock_get.call_count, 3)

        # Verify no sleep was called (ReadTimeout doesn't trigger sleep)
        mock_sleep.assert_not_called()

        # Verify API calls were correct
        for call in mock_get.call_args_list:
            args, kwargs = call
            self.assertEqual(args[0], "https://api.github.com/users/test-user")
            self.assertEqual(kwargs["headers"]["Authorization"], "Bearer fake-token")


class TestGitHubAPI(unittest.TestCase):
    """Test GitHub API interaction functionality"""

    def setUp(self):
        self.mock_response = MagicMock()
        self.mock_response.status_code = 200

        # Sample issue data that won't change
        self.sample_issues = [
            {
                "title": "deposit journal.com doi:10.1234/test",
                "body": "test body",
                "number": 1,
                "user": {"login": "test-user"},
                "created_at": "2024-01-01T00:00:00Z",
                "html_url": "https://github.com/test-org/test-repo/issues/1",
                "labels": [],
            }
        ]

        # Setup environment variables
        self.env_patcher = patch.dict(
            "os.environ",
            {"GH_TOKEN": "fake-token", "GITHUB_REPOSITORY": "test-org/test-repo"},
        )
        self.env_patcher.start()

    def tearDown(self):
        """Clean up after each test"""
        self.env_patcher.stop()

    @patch("requests.get")
    def test_get_open_issues_success(self, mock_get):
        """Test successful retrieval of open issues"""
        self.mock_response.json.return_value = self.sample_issues
        mock_get.return_value = self.mock_response

        with patch.dict("os.environ", {"GH_TOKEN": "fake-token"}):
            issues = get_open_issues()

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["title"], "deposit journal.com doi:10.1234/test")
        self.assertEqual(issues[0]["number"], "1")

        # Verify API call
        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer fake-token")
        self.assertEqual(kwargs["params"]["state"], "open")

    @patch("requests.get")
    def test_get_open_issues_404(self, mock_get):
        """Test handling of 404 response"""
        self.mock_response.status_code = 404
        mock_get.return_value = self.mock_response

        with patch.dict("os.environ", {"GH_TOKEN": "fake-token"}):
            issues = get_open_issues()

        self.assertEqual(issues, [])

    @patch("requests.get")
    @patch("time.sleep")
    @patch("time.time")
    def test_rate_limit_retry(self, mock_time, mock_sleep, mock_get):
        """Test retry behavior when hitting rate limits"""
        # Mock current time to have consistent test behavior
        current_time = 1000000
        mock_time.return_value = current_time

        # Setup mock responses
        rate_limited_response = MagicMock()
        rate_limited_response.status_code = 403
        rate_limited_response.headers = {
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(current_time + 30),  # Reset in 30 seconds
        }

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = [
            {
                "title": "deposit Test Issue",
                "body": "Test Body",
                "number": 1,
                "user": {"login": "test-user"},
                "created_at": "2024-01-01T00:00:00Z",
                "html_url": "https://github.com/test/1",
                "labels": [],
            }
        ]

        # First call hits rate limit, second call succeeds
        mock_get.side_effect = [rate_limited_response, success_response]

        with patch.dict("os.environ", {"GH_TOKEN": "fake-token"}):
            issues = get_open_issues()

        # Verify rate limit handling
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["title"], "deposit Test Issue")

        # Verify sleep was called with exactly 30 seconds
        mock_sleep.assert_called_once_with(30)

        # Verify correct API calls
        self.assertEqual(mock_get.call_count, 2)
        for call in mock_get.call_args_list:
            args, kwargs = call
            self.assertEqual(kwargs["params"]["state"], "open")
            self.assertEqual(kwargs["headers"]["Authorization"], "Bearer fake-token")

    @patch("requests.get")
    def test_network_error_retry(self, mock_get):
        """Test retry behavior on network errors"""
        mock_get.side_effect = RequestException("Network error")

        with patch.dict("os.environ", {"GH_TOKEN": "fake-token"}):
            with self.assertRaises(RuntimeError) as context:
                get_open_issues()

        self.assertIn("Failed to fetch issues after 3 attempts", str(context.exception))
        self.assertEqual(mock_get.call_count, 3)  # Verify 3 retry attempts

    @patch("requests.get")
    def test_get_open_issues_all_attempts_fail(self, mock_get):
        """Test that empty list is returned when all attempts fail without exception"""
        # Create response that fails but doesn't trigger retry logic
        failed_response = MagicMock()
        failed_response.status_code = 403
        # No rate limit headers, so won't trigger rate limit retry logic
        failed_response.headers = {}

        # Make all attempts return the same failed response
        mock_get.return_value = failed_response

        with patch.dict("os.environ", {"GH_TOKEN": "fake-token"}):
            issues = get_open_issues()

        # Verify empty list is returned
        self.assertEqual(issues, [])

        # Verify we tried MAX_RETRIES times
        self.assertEqual(mock_get.call_count, 3)

    @patch("requests.get")
    @patch("time.sleep")
    @patch("time.time")
    def test_rate_limit_already_expired(self, mock_time, mock_sleep, mock_get):
        """Test rate limit handling when reset time is in the past"""
        # Mock current time
        current_time = 1000000
        mock_time.return_value = current_time

        # Setup response with expired rate limit
        rate_limited_response = MagicMock()
        rate_limited_response.status_code = 403
        rate_limited_response.headers = {
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(current_time - 30),  # Reset time in the past
        }

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = [
            {
                "title": "deposit Test Issue",
                "body": "Test Body",
                "number": 1,
                "user": {"login": "test-user"},
                "created_at": "2024-01-01T00:00:00Z",
                "html_url": "https://github.com/test/1",
                "labels": [],
            }
        ]

        # First call hits expired rate limit, second call succeeds
        mock_get.side_effect = [rate_limited_response, success_response]

        with patch.dict("os.environ", {"GH_TOKEN": "fake-token"}):
            issues = get_open_issues()

        # Verify rate limit handling
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["title"], "deposit Test Issue")

        # Verify sleep was NOT called since rate limit was already expired
        mock_sleep.assert_not_called()

        # Verify correct API calls
        self.assertEqual(mock_get.call_count, 2)


class TestAnswerFunction(unittest.TestCase):
    """Test the answer function that updates GitHub issues"""

    def setUp(self):
        """Set up test environment before each test"""
        self.base_url = "https://api.github.com/repos/test-org/test-repo/issues"
        self.headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer fake-token",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self.issue_number = "123"

        # Setup environment variables
        self.env_patcher = patch.dict(
            "os.environ",
            {"GH_TOKEN": "fake-token", "GITHUB_REPOSITORY": "test-org/test-repo"},
        )
        self.env_patcher.start()

    def tearDown(self):
        """Clean up after each test"""
        self.env_patcher.stop()

    @patch("requests.post")
    @patch("requests.patch")
    def test_answer_valid_authorized(self, mock_patch, mock_post):
        """Test answering a valid issue from authorized user"""
        # Setup mock responses
        mock_post.return_value.status_code = 201
        mock_patch.return_value.status_code = 200

        # Call function
        answer(
            is_valid=True,
            message="Thank you for your contribution!",
            issue_number=self.issue_number,
            is_authorized=True,
        )

        # Verify label API call
        mock_post.assert_any_call(
            f"{self.base_url}/{self.issue_number}/labels",
            headers=self.headers,
            json={"labels": ["to be processed"]},
            timeout=30,
        )

        # Verify comment API call
        mock_post.assert_any_call(
            f"{self.base_url}/{self.issue_number}/comments",
            headers=self.headers,
            json={"body": "Thank you for your contribution!"},
            timeout=30,
        )

        # Verify issue closure API call
        mock_patch.assert_called_once_with(
            f"{self.base_url}/{self.issue_number}",
            headers=self.headers,
            json={"state": "closed"},
            timeout=30,
        )

    @patch("requests.post")
    @patch("requests.patch")
    def test_answer_invalid_authorized(self, mock_patch, mock_post):
        """Test answering an invalid issue from authorized user"""
        answer(
            is_valid=False,
            message="Invalid format",
            issue_number=self.issue_number,
            is_authorized=True,
        )

        # Verify correct label was used
        mock_post.assert_any_call(
            f"{self.base_url}/{self.issue_number}/labels",
            headers=self.headers,
            json={"labels": ["invalid"]},
            timeout=30,
        )

    @patch("requests.post")
    @patch("requests.patch")
    def test_answer_unauthorized(self, mock_patch, mock_post):
        """Test answering an issue from unauthorized user"""
        answer(
            is_valid=False,
            message="Unauthorized user",
            issue_number=self.issue_number,
            is_authorized=False,
        )

        # Verify correct label was used
        mock_post.assert_any_call(
            f"{self.base_url}/{self.issue_number}/labels",
            headers=self.headers,
            json={"labels": ["rejected"]},
            timeout=30,
        )

    @patch("requests.post")
    def test_answer_label_error(self, mock_post):
        """Test handling of API error when adding label"""
        mock_post.side_effect = RequestException("Network error")

        with self.assertRaises(RequestException):
            answer(
                is_valid=True,
                message="Test message",
                issue_number=self.issue_number,
            )

    @patch("requests.post")
    @patch("requests.patch")
    def test_answer_comment_error(self, mock_patch, mock_post):
        """Test handling of API error when adding comment"""
        # First post (label) succeeds, second post (comment) fails
        mock_post.side_effect = [
            MagicMock(status_code=201),
            RequestException("Network error"),
        ]

        with self.assertRaises(RequestException):
            answer(
                is_valid=True,
                message="Test message",
                issue_number=self.issue_number,
            )

    @patch("requests.post")
    @patch("requests.patch")
    def test_answer_close_error(self, mock_patch, mock_post):
        """Test handling of API error when closing issue"""
        mock_post.return_value = MagicMock(status_code=201)
        mock_patch.side_effect = RequestException("Network error")

        with self.assertRaises(RequestException):
            answer(
                is_valid=True,
                message="Test message",
                issue_number=self.issue_number,
            )


class TestZenodoDeposit(unittest.TestCase):
    """Test Zenodo deposit functionality"""

    def setUp(self):
        """Set up test environment before each test"""
        self.env_patcher = patch.dict(
            "os.environ",
            {
                "ZENODO_SANDBOX": "fake-sandbox-token",
                "ZENODO_PRODUCTION": "fake-prod-token",
                "ENVIRONMENT": "development",
            },
        )
        self.env_patcher.start()

        self.test_data = [
            {
                "data": {
                    "title": "test deposit",
                    "metadata": [{"id": "1", "title": "Test"}],
                    "citations": [{"citing": "1", "cited": "2"}],
                },
                "provenance": {
                    "generatedAtTime": "2024-01-01T00:00:00Z",
                    "wasAttributedTo": 12345,
                    "hadPrimarySource": "https://github.com/test/1",
                },
            }
        ]

    def tearDown(self):
        """Clean up after each test"""
        self.env_patcher.stop()
        if os.path.exists("data_to_store.json"):
            os.remove("data_to_store.json")

    @patch("requests.post")
    def test_create_deposition_resource(self, mock_post):
        """Test creation of Zenodo deposition resource"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": "12345",
            "links": {"bucket": "https://sandbox.zenodo.org/api/bucket/12345"},
        }
        mock_post.return_value = mock_response

        deposition_id, bucket = _create_deposition_resource(
            "2024-01-01", base_url="https://sandbox.zenodo.org/api"
        )

        self.assertEqual(deposition_id, "12345")
        self.assertEqual(bucket, "https://sandbox.zenodo.org/api/bucket/12345")

        # Verify API call
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args

        self.assertEqual(kwargs["params"], {"access_token": "fake-sandbox-token"})
        self.assertEqual(kwargs["headers"], {"Content-Type": "application/json"})
        self.assertEqual(kwargs["timeout"], 30)

    @patch("requests.put")
    def test_upload_data(self, mock_put):
        """Test uploading data file to Zenodo"""
        mock_put.return_value.status_code = 200
        mock_put.return_value.raise_for_status = lambda: None

        # Create test file
        with open("data_to_store.json", "w") as f:
            json.dump({"test": "data"}, f)

        _upload_data(
            "2024-01-01",
            "https://sandbox.zenodo.org/api/bucket/12345",
            base_url="https://sandbox.zenodo.org/api",
        )

        # Verify API call
        mock_put.assert_called_once()
        args, kwargs = mock_put.call_args

        self.assertEqual(
            args[0],
            "https://sandbox.zenodo.org/api/bucket/12345/2024-01-01_weekly_deposit.json",
        )
        self.assertEqual(kwargs["params"], {"access_token": "fake-sandbox-token"})
        self.assertEqual(kwargs["timeout"], 30)

    @patch("crowdsourcing.process_issues._create_deposition_resource")
    @patch("crowdsourcing.process_issues._upload_data")
    @patch("requests.post")
    def test_deposit_on_zenodo(self, mock_post, mock_upload, mock_create):
        """Test full Zenodo deposit process"""
        # Setup mocks
        mock_create.return_value = (
            "12345",
            "https://sandbox.zenodo.org/api/bucket/12345",
        )
        mock_post.return_value.status_code = 202  # Changed from 200 to 202 for publish
        mock_post.return_value.text = ""  # Add this to avoid MagicMock text in error

        deposit_on_zenodo(self.test_data)

        # Verify API calls order and parameters
        mock_create.assert_called_once_with(
            datetime.now().strftime("%Y-%m-%d"),
            base_url="https://sandbox.zenodo.org/api",  # Add base_url
        )
        mock_upload.assert_called_once_with(
            datetime.now().strftime("%Y-%m-%d"),
            "https://sandbox.zenodo.org/api/bucket/12345",
            base_url="https://sandbox.zenodo.org/api",  # Add base_url
        )

        # Verify publish request
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(
            args[0],
            "https://sandbox.zenodo.org/api/deposit/depositions/12345/actions/publish",
        )
        self.assertEqual(kwargs["params"], {"access_token": "fake-sandbox-token"})
        self.assertEqual(kwargs["timeout"], 30)

        # Verify cleanup happened
        self.assertFalse(os.path.exists("data_to_store.json"))

    @patch("requests.post")
    def test_create_deposition_resource_error(self, mock_post):
        """Test error handling in deposition creation"""
        mock_post.side_effect = requests.RequestException("API Error")

        with self.assertRaises(requests.RequestException):
            _create_deposition_resource("2024-01-01")

    @patch("requests.put")
    def test_upload_data_error(self, mock_put):
        """Test error handling in data upload"""
        mock_put.side_effect = requests.RequestException("Upload Error")

        with open("data_to_store.json", "w") as f:
            json.dump({"test": "data"}, f)

        with self.assertRaises(requests.RequestException):
            _upload_data("2024-01-01", "https://zenodo.org/api/bucket/12345")

    @patch("crowdsourcing.process_issues._create_deposition_resource")
    def test_deposit_on_zenodo_create_error(self, mock_create):
        """Test error handling in full deposit process - creation error"""
        mock_create.side_effect = requests.RequestException("Creation Error")

        with self.assertRaises(requests.RequestException):
            deposit_on_zenodo(self.test_data)

        # Verify cleanup happened
        self.assertFalse(os.path.exists("data_to_store.json"))

    def test_deposit_development_environment(self):
        """Test deposit in development environment uses sandbox"""
        with patch("requests.post") as mock_post, patch("requests.put") as mock_put:
            # Mock create deposition
            mock_post.return_value.json.return_value = {
                "id": "12345",
                "links": {"bucket": "https://sandbox.zenodo.org/api/bucket/12345"},
            }
            mock_post.return_value.status_code = 201

            # Mock upload
            mock_put.return_value.status_code = 200
            mock_put.return_value.raise_for_status = lambda: None

            # Mock publish
            mock_post.return_value.status_code = 202

            deposit_on_zenodo(self.test_data)

            # Verify sandbox URL was used
            calls = mock_post.call_args_list
            self.assertTrue(any("sandbox.zenodo.org" in call[0][0] for call in calls))

    def test_deposit_production_environment(self):
        """Test deposit in production environment uses main Zenodo"""
        with patch.dict("os.environ", {"ENVIRONMENT": "production"}):
            with patch("requests.post") as mock_post, patch("requests.put") as mock_put:
                # Mock create deposition
                mock_post.return_value.json.return_value = {
                    "id": "12345",
                    "links": {"bucket": "https://zenodo.org/api/bucket/12345"},
                }
                mock_post.return_value.status_code = 201

                # Mock upload
                mock_put.return_value.status_code = 200
                mock_put.return_value.raise_for_status = lambda: None

                # Mock publish
                mock_post.return_value.status_code = 202

                deposit_on_zenodo(self.test_data)

                # Verify production URL was used
                calls = mock_post.call_args_list
                self.assertTrue(
                    all("sandbox.zenodo.org" not in call[0][0] for call in calls)
                )

    def test_get_zenodo_token_development(self):
        """Test getting Zenodo token in development environment"""
        token = _get_zenodo_token()
        self.assertEqual(token, "fake-sandbox-token")

    def test_get_zenodo_token_production(self):
        """Test getting Zenodo token in production environment"""
        with patch.dict("os.environ", {"ENVIRONMENT": "production"}):
            token = _get_zenodo_token()
            self.assertEqual(token, "fake-prod-token")

    def test_get_zenodo_token_missing(self):
        """Test error when token is missing"""
        with patch.dict(
            "os.environ", {"ZENODO_SANDBOX": "", "ENVIRONMENT": "development"}
        ):
            with self.assertRaises(ValueError) as context:
                _get_zenodo_token()
            self.assertIn("ZENODO_SANDBOX token not found", str(context.exception))

    def test_get_zenodo_token_missing_production(self):
        """Test error when production token is missing"""
        with patch.dict(
            "os.environ",
            {
                "ENVIRONMENT": "production",
                "ZENODO_PRODUCTION": "",  # Token mancante
            },
        ):
            with self.assertRaises(ValueError) as context:
                _get_zenodo_token()
            self.assertIn("ZENODO_PRODUCTION token not found", str(context.exception))

    @patch("crowdsourcing.process_issues._create_deposition_resource")
    @patch("crowdsourcing.process_issues._upload_data")
    @patch("requests.post")
    def test_deposit_on_zenodo_publish_error(self, mock_post, mock_upload, mock_create):
        """Test error handling when publish fails"""
        # Setup mocks
        mock_create.return_value = (
            "12345",
            "https://sandbox.zenodo.org/api/bucket/12345",
        )
        mock_post.return_value.status_code = 400  # Simula errore di pubblicazione
        mock_post.return_value.text = "Publication failed"

        with self.assertRaises(Exception) as context:
            deposit_on_zenodo(self.test_data)

        self.assertEqual(
            str(context.exception), "Failed to publish deposition: Publication failed"
        )

        # Verify cleanup happened even after error
        self.assertFalse(os.path.exists("data_to_store.json"))


class TestProcessOpenIssues(unittest.TestCase):
    """Test the main process_open_issues function"""

    def setUp(self):
        """Set up test environment"""
        self.env_patcher = patch.dict(
            "os.environ", {"GH_TOKEN": "fake-gh-token", "ZENODO": "fake-zenodo-token"}
        )
        self.env_patcher.start()

        # Sample issue data with properly formatted CSV and valid DOI
        self.sample_issue = {
            "title": "deposit journal.com doi:10.1007/s42835-022-01029-y",
            "body": """"id","title","author","pub_date","venue","volume","issue","page","type","publisher","editor"
"doi:10.1007/s42835-022-01029-y","Test Title","Test Author","2024","Test Journal","1","1","1-10","journal article","Test Publisher",""
"doi:10.1007/978-3-030-00668-6_8","Cited Paper","Another Author","2024","Another Journal","2","2","20-30","journal article","Test Publisher",""
===###===@@@===
"citing_id","cited_id"
"doi:10.1007/s42835-022-01029-y","doi:10.1007/978-3-030-00668-6_8\"""",
            "number": "1",
            "author": {"login": "test-user"},
            "createdAt": "2024-01-01T00:00:00Z",
            "url": "https://github.com/test/1",
        }

    def tearDown(self):
        """Clean up after each test"""
        self.env_patcher.stop()

    @patch("crowdsourcing.process_issues.get_open_issues")
    @patch("crowdsourcing.process_issues.get_user_id")
    @patch("crowdsourcing.process_issues.is_in_safe_list")
    @patch("crowdsourcing.process_issues.deposit_on_zenodo")
    @patch("crowdsourcing.process_issues.answer")
    def test_process_valid_authorized_issue(
        self, mock_answer, mock_deposit, mock_safe_list, mock_user_id, mock_get_issues
    ):
        """Test processing a valid issue from authorized user"""
        # Setup mocks
        mock_get_issues.return_value = [self.sample_issue]
        mock_user_id.return_value = 12345
        mock_safe_list.return_value = True

        # Run function
        process_open_issues()

        # Verify user validation
        mock_user_id.assert_called_once_with("test-user")
        mock_safe_list.assert_called_once_with(12345)

        # Verify issue was processed
        mock_answer.assert_called_once()
        args, kwargs = mock_answer.call_args
        self.assertTrue(args[0])  # is_valid
        self.assertIn("Thank you", args[1])  # message
        self.assertEqual(args[2], "1")  # issue_number
        self.assertTrue(kwargs["is_authorized"])

        # Verify data was deposited
        mock_deposit.assert_called_once()
        args, kwargs = mock_deposit.call_args
        deposited_data = args[0][0]
        self.assertEqual(deposited_data["data"]["title"], self.sample_issue["title"])
        self.assertEqual(
            deposited_data["provenance"]["wasAttributedTo"],
            f"https://api.github.com/user/{12345}",
        )

    @patch("crowdsourcing.process_issues.get_open_issues")
    @patch("crowdsourcing.process_issues.get_user_id")
    @patch("crowdsourcing.process_issues.is_in_safe_list")
    @patch("crowdsourcing.process_issues.deposit_on_zenodo")
    @patch("crowdsourcing.process_issues.answer")
    def test_process_unauthorized_user(
        self, mock_answer, mock_deposit, mock_safe_list, mock_user_id, mock_get_issues
    ):
        """Test processing an issue from unauthorized user"""
        # Setup mocks
        mock_get_issues.return_value = [self.sample_issue]
        mock_user_id.return_value = 12345
        mock_safe_list.return_value = False

        # Run function
        process_open_issues()

        # Verify user was checked but not authorized
        mock_user_id.assert_called_once_with("test-user")
        mock_safe_list.assert_called_once_with(12345)

        # Verify appropriate response
        mock_answer.assert_called_once()
        args, kwargs = mock_answer.call_args
        self.assertFalse(args[0])  # is_valid
        self.assertIn("register as a trusted user", args[1])  # message
        self.assertEqual(args[2], "1")  # issue_number
        self.assertFalse(kwargs["is_authorized"])

        # Verify no deposit was made
        mock_deposit.assert_not_called()

    @patch("crowdsourcing.process_issues.get_open_issues")
    @patch("crowdsourcing.process_issues.get_user_id")
    @patch("crowdsourcing.process_issues.is_in_safe_list")
    @patch("crowdsourcing.process_issues.validate")
    @patch("crowdsourcing.process_issues.get_data_to_store")
    @patch("crowdsourcing.process_issues.answer")
    @patch("crowdsourcing.process_issues.deposit_on_zenodo")
    def test_process_open_issues_data_processing_error(
        self,
        mock_deposit,
        mock_answer,
        mock_get_data,
        mock_validate,
        mock_safe_list,
        mock_user_id,
        mock_get_issues,
    ):
        """Test handling of get_data_to_store error for an issue"""
        # Setup mocks
        mock_get_issues.return_value = [self.sample_issue]
        mock_user_id.return_value = 12345
        mock_safe_list.return_value = True
        mock_validate.return_value = (True, "Valid data")
        mock_get_data.side_effect = Exception("Data processing error")

        # Run function
        process_open_issues()

        # Verify error was handled and processing continued
        mock_get_data.assert_called_once()
        mock_answer.assert_called_once()
        # Verify deposit wasn't attempted since no valid data was processed
        mock_deposit.assert_not_called()

    @patch("crowdsourcing.process_issues.get_open_issues")
    @patch("crowdsourcing.process_issues.get_user_id")
    @patch("crowdsourcing.process_issues.is_in_safe_list")
    @patch("crowdsourcing.process_issues.validate")
    @patch("crowdsourcing.process_issues.get_data_to_store")
    @patch("crowdsourcing.process_issues.answer")
    @patch("crowdsourcing.process_issues.deposit_on_zenodo")
    def test_process_open_issues_zenodo_deposit_error(
        self,
        mock_deposit,
        mock_answer,
        mock_get_data,
        mock_validate,
        mock_safe_list,
        mock_user_id,
        mock_get_issues,
    ):
        """Test handling of Zenodo deposit error"""
        # Setup mocks
        mock_get_issues.return_value = [self.sample_issue]
        mock_user_id.return_value = 12345
        mock_safe_list.return_value = True
        mock_validate.return_value = (True, "Valid data")
        mock_get_data.return_value = {"test": "data"}
        mock_deposit.side_effect = Exception("Zenodo deposit error")

        # Verify the Zenodo deposit error is re-raised
        with self.assertRaises(Exception) as context:
            process_open_issues()

        self.assertEqual(str(context.exception), "Zenodo deposit error")
        mock_deposit.assert_called_once()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
