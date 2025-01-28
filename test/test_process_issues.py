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

import os
import time
import unittest
from unittest.mock import MagicMock, patch

from process_issues import (
    _validate_title,
    answer,
    get_open_issues,
    get_user_id,
    is_in_safe_list,
    process_open_issues,
    validate,
)
from requests.exceptions import RequestException


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


class TestValidation(unittest.TestCase):
    def test_valid_issue(self):
        """Test that a valid issue with correct title and CSV data is accepted"""
        title = "deposit journal.com doi:10.1007/s42835-022-01029-y"
        body = """"id","title","author","pub_date","venue","volume","issue","page","type","publisher","editor"
"doi:10.1007/978-3-662-07918-8_3","Influence of Dielectric Properties, State, and Electrodes on Electric Strength","Ushakov, Vasily Y.","2004","Insulation of High-Voltage Equipment [isbn:9783642058530 isbn:9783662079188]","","","27-82","book chapter","Springer Science and Business Media LLC [crossref:297]",""
"doi:10.1016/0021-9991(73)90147-2","Flux-corrected transport. I. SHASTA, a fluid transport algorithm that works","Boris, Jay P; Book, David L","1973-1","Journal of Computational Physics [issn:0021-9991]","11","1","38-69","journal article","Elsevier BV [crossref:78]",""
===###===@@@===
"citing_id","cited_id"
"doi:10.1007/s42835-022-01029-y","doi:10.1007/978-3-662-07918-8_3"
"doi:10.1007/s42835-022-01029-y","doi:10.1016/0021-9991(73)90147-2\""""
        is_valid, message = validate(title, body)
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
        is_valid, message = validate(title, body)
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
        is_valid, message = validate(title, body)
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
        is_valid, message = validate(title, body)
        self.assertFalse(is_valid)
        self.assertIn("could not be processed as a CSV", message)


class TestUserValidation(unittest.TestCase):
    def setUp(self):
        # Create a real safe list file with actual GitHub user IDs
        with open("safe_list.txt", "w") as f:
            # These are real GitHub user IDs
            f.write("3869247\n")  # The ID of essepuntato
            f.write("42008604\n")  # The ID of arcangelo7

    def tearDown(self):
        # Clean up the test file
        if os.path.exists("safe_list.txt"):
            os.remove("safe_list.txt")

    def test_get_user_id_real_user(self):
        """Test getting ID of a real GitHub user"""
        user_id = get_user_id("arcangelo7")
        self.assertEqual(user_id, 42008604)

    def test_get_user_id_nonexistent_user(self):
        """Test getting ID of a nonexistent GitHub user"""
        user_id = get_user_id("this_user_definitely_does_not_exist_123456789")
        self.assertIsNone(user_id)

    def test_is_in_safe_list_allowed_user(self):
        """Test with a real allowed GitHub user ID"""
        self.assertTrue(is_in_safe_list(42008604))  # arcangelo7's ID

    def test_is_in_safe_list_not_allowed_user(self):
        """Test with a real but not allowed GitHub user ID"""
        self.assertFalse(is_in_safe_list(106336590))  # vbrandelero's ID

    def test_is_in_safe_list_nonexistent_user(self):
        """Test with a nonexistent user ID"""
        self.assertFalse(is_in_safe_list(999999999))


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
                "html_url": "https://github.com/test/test/issues/1",
            }
        ]

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
        self.assertEqual(kwargs["params"]["labels"], "deposit")

    @patch("requests.get")
    def test_get_open_issues_404(self, mock_get):
        """Test handling of 404 response"""
        self.mock_response.status_code = 404
        mock_get.return_value = self.mock_response

        with patch.dict("os.environ", {"GH_TOKEN": "fake-token"}):
            issues = get_open_issues()

        self.assertEqual(issues, [])

    @patch("requests.get")
    @patch("time.sleep")  # Mock sleep to speed up tests
    def test_rate_limit_handling(self, mock_sleep, mock_get):
        """Test handling of rate limiting"""
        # First response indicates rate limit hit
        rate_limited_response = MagicMock()
        rate_limited_response.status_code = 403
        rate_limited_response.headers = {
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(int(time.time()) + 3600),
        }

        # Second response succeeds
        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = self.sample_issues

        mock_get.side_effect = [rate_limited_response, success_response]

        with patch.dict("os.environ", {"GH_TOKEN": "fake-token"}):
            issues = get_open_issues()

        self.assertEqual(len(issues), 1)
        self.assertTrue(mock_sleep.called)

    @patch("requests.get")
    def test_network_error_retry(self, mock_get):
        """Test retry behavior on network errors"""
        mock_get.side_effect = RequestException("Network error")

        with patch.dict("os.environ", {"GH_TOKEN": "fake-token"}):
            with self.assertRaises(RuntimeError) as context:
                get_open_issues()

        self.assertIn("Failed to fetch issues after 3 attempts", str(context.exception))
        self.assertEqual(mock_get.call_count, 3)  # Verify 3 retry attempts


class TestAnswerFunction(unittest.TestCase):
    """Test the answer function that updates GitHub issues"""

    def setUp(self):
        """Set up test environment before each test"""
        self.base_url = (
            "https://api.github.com/repos/opencitations/crowdsourcing/issues"
        )
        self.headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer fake-token",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self.issue_number = "123"

        # Setup environment variable
        self.env_patcher = patch.dict("os.environ", {"GH_TOKEN": "fake-token"})
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


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
