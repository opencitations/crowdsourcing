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

from process_issues import _validate_title, validate
import unittest


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
        self.assertIn("title of the issue was not structured correctly", message)

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


if __name__ == "__main__":
    unittest.main()
