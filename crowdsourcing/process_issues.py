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


import csv
import io
import json
import logging
import os
import re
import shutil
import time
from datetime import datetime
from typing import List, Optional, Tuple

import requests
import yaml
from oc_ds_converter.oc_idmanager.base import IdentifierManager
from oc_ds_converter.oc_idmanager.doi import DOIManager
from oc_ds_converter.oc_idmanager.isbn import ISBNManager
from oc_ds_converter.oc_idmanager.openalex import OpenAlexManager
from oc_ds_converter.oc_idmanager.pmcid import PMCIDManager
from oc_ds_converter.oc_idmanager.pmid import PMIDManager
from oc_ds_converter.oc_idmanager.url import URLManager
from oc_ds_converter.oc_idmanager.wikidata import WikidataManager
from oc_ds_converter.oc_idmanager.wikipedia import WikipediaManager
from oc_validator.interface.gui import make_gui, merge_html_files
from oc_validator.main import ClosureValidator
from crowdsourcing.archive_manager import ArchiveManager
from crowdsourcing.zenodo_utils import create_deposition_resource, get_zenodo_token

# Constants
SAFE_LIST_PATH = "safe_list.yaml"

# Initialize archive manager
archive_manager = ArchiveManager()


def _validate_title(title: str) -> Tuple[bool, str]:
    """Validate the format and identifier in an issue title."""
    basic_format = re.search(
        r"deposit\s+(.+?)\s+[a-zA-Z]+:.+",
        title,
        re.IGNORECASE,
    )
    if not basic_format:
        return (
            False,
            'The title of the issue was not structured correctly. Please, follow this format: deposit {domain name of journal} {doi or other supported identifier}. For example "deposit localhost:330 doi:10.1007/978-3-030-00668-6_8". The following identifiers are currently supported: doi, isbn, pmid, pmcid, url, wikidata, wikipedia, and openalex',
        )

    match = re.search(
        r"deposit\s+(.+?)\s+([a-zA-Z]+):(.+)",
        title,
        re.IGNORECASE,
    )

    identifier_schema = match.group(2).lower()
    identifier = match.group(3)

    # Map of identifier types to their manager classes
    manager_map = {
        "doi": DOIManager,
        "isbn": ISBNManager,
        "pmid": PMIDManager,
        "pmcid": PMCIDManager,
        "url": URLManager,
        "wikidata": WikidataManager,
        "wikipedia": WikipediaManager,
        "openalex": OpenAlexManager,
    }

    manager_class = manager_map.get(identifier_schema)
    if not manager_class:
        return False, f"The identifier schema '{identifier_schema}' is not supported"

    # Use API service for all identifiers that require online validation
    needs_api = {"doi", "pmid", "pmcid", "url", "wikidata", "wikipedia", "openalex"}
    id_manager: IdentifierManager = (
        manager_class(use_api_service=True)
        if identifier_schema in needs_api
        else manager_class()
    )
    is_valid = id_manager.is_valid(identifier)

    if not is_valid:
        return (
            False,
            f"The identifier with literal value {identifier} specified in the issue title is not a valid {identifier_schema.upper()}",
        )
    return True, ""


def validate(
    issue_title: str,
    issue_body: str,
    issue_number: str,
    validation_output_dir: str = "validation_output",
    validation_reports_dir: str = "docs/validation_reports",
) -> Tuple[bool, str]:
    """Validate issue title and body content using oc_validator.

    Args:
        issue_title: Title of the GitHub issue
        issue_body: Body content of the GitHub issue
        issue_number: GitHub issue number to update
        validation_output_dir: Directory for temporary validation output files
        validation_reports_dir: Directory where validation reports will be stored

    Returns:
        Tuple containing:
        - bool: Whether the content is valid
        - str: Validation message or error details
    """
    logger = logging.getLogger(__name__)

    logger.info("Starting validation")
    logger.info(f"Validating title: {issue_title}")

    # First validate the title format
    is_valid_title, title_message = _validate_title(issue_title)
    if not is_valid_title:
        logger.warning(f"Invalid title format: {title_message}")
        return False, title_message

    # Check if body is empty
    if not issue_body:
        logger.warning("Empty issue body")
        return (
            False,
            "The issue body cannot be empty. Please provide metadata and citations in CSV format separated by '===###===@@@===', as shown in the guide: https://github.com/opencitations/crowdsourcing/blob/main/README.md",
        )

    # Check for required separator
    if "===###===@@@===" not in issue_body:
        logger.warning("Missing required separator in issue body")
        return (
            False,
            'Please use the separator "===###===@@@===" to divide metadata from citations, as shown in the following guide: https://github.com/opencitations/crowdsourcing/blob/main/README.md',
        )

    try:
        logger.info("Creating validation output directory")
        os.makedirs(validation_output_dir, exist_ok=True)
        os.makedirs(validation_reports_dir, exist_ok=True)

        # Split the data into metadata and citations
        split_data = issue_body.split("===###===@@@===")
        metadata_csv = split_data[0].strip()
        citations_csv = split_data[1].strip()

        # Create temporary files for validation
        with open("temp_metadata.csv", "w", encoding="utf-8") as f:
            f.write(metadata_csv)
        with open("temp_citations.csv", "w", encoding="utf-8") as f:
            f.write(citations_csv)

        # Initialize and run validator
        validator = ClosureValidator(
            meta_csv_doc="temp_metadata.csv",
            meta_output_dir=validation_output_dir,
            cits_csv_doc="temp_citations.csv",
            cits_output_dir=validation_output_dir,
            strict_sequenciality=True,
            meta_kwargs={"verify_id_existence": True},
            cits_kwargs={"verify_id_existence": True},
        )

        # Get validation results
        validation_result = validator.validate()

        # Check if there are any validation errors
        has_meta_errors = (
            os.path.exists(f"{validation_output_dir}/meta_validation_summary.txt")
            and os.path.getsize(f"{validation_output_dir}/meta_validation_summary.txt")
            > 0
        )
        has_cits_errors = (
            os.path.exists(f"{validation_output_dir}/cits_validation_summary.txt")
            and os.path.getsize(f"{validation_output_dir}/cits_validation_summary.txt")
            > 0
        )

        if has_meta_errors or has_cits_errors:
            # Generate HTML report for validation errors
            report_filename = f"validation_issue_{issue_number}.html"
            report_path = f"{validation_reports_dir}/{report_filename}"

            # Generate metadata report if there were metadata errors
            if has_meta_errors:
                make_gui(
                    "temp_metadata.csv",
                    f"{validation_output_dir}/out_validate_meta.json",
                    f"{validation_output_dir}/meta_report.html",
                )

            # Generate citations report if there were citation errors
            if has_cits_errors:
                make_gui(
                    "temp_citations.csv",
                    f"{validation_output_dir}/out_validate_cits.json",
                    f"{validation_output_dir}/cits_report.html",
                )

            # Merge reports if both exist, otherwise copy the single report
            if has_meta_errors and has_cits_errors:
                merge_html_files(
                    f"{validation_output_dir}/meta_report.html",
                    f"{validation_output_dir}/cits_report.html",
                    report_path,
                )
            elif has_meta_errors:
                shutil.copy(f"{validation_output_dir}/meta_report.html", report_path)
            else:  # has_cits_errors
                shutil.copy(f"{validation_output_dir}/cits_report.html", report_path)

            # Get repository from environment and construct report URL
            repository = os.environ["GITHUB_REPOSITORY"]
            base_url = f"https://{repository.split('/')[0]}.github.io/{repository.split('/')[1]}"
            report_url = f"{base_url}/validation_reports/{report_filename}"

            # Add report to archive manager
            archive_manager.add_report(report_filename, report_url)

            # Create error message based on which parts have errors
            error_parts = []
            if has_meta_errors:
                error_parts.append("metadata")
            if has_cits_errors:
                error_parts.append("citations")

            # Use index.html with report parameter for redirection
            error_message = f"Validation errors found in {' and '.join(error_parts)}. Please check the detailed validation report: {base_url}/validation_reports/index.html?report={report_filename}"
            return False, error_message

        # If no validation errors, return success
        return (
            True,
            "Thank you for your contribution! OpenCitations just processed the data you provided. The citations will soon be available on the [OpenCitations Index](https://opencitations.net/index) and metadata on [OpenCitations Meta](https://opencitations.net/meta)",
        )

    except Exception as e:
        logger.error(f"Validation error: {e}")
        return (
            False,
            f"Error validating data: {str(e)}. Please ensure both metadata and citations are valid CSVs following the required format.",
        )
    finally:
        # Clean up temporary files in all cases
        cleanup_files = [
            "temp_metadata.csv",
            "temp_citations.csv",
        ]
        for file in cleanup_files:
            if os.path.exists(file):
                os.remove(file)

        if os.path.exists(validation_output_dir):
            shutil.rmtree(validation_output_dir)


def answer(
    is_valid: bool, message: str, issue_number: str, is_authorized: bool = True
) -> None:
    """Update issue status and add comment using GitHub REST API.

    Args:
        is_valid: Whether the issue content is valid
        message: Comment message to add
        issue_number: GitHub issue number to update
        is_authorized: Whether the user is authorized (in safe list)
    """
    print(f"Updating issue #{issue_number}")
    # Determine label based on validation and authorization
    if not is_authorized:
        label = "rejected"
    elif not is_valid:
        label = "invalid"
    else:
        label = "to be processed"

    print(f"Adding label '{label}' to issue #{issue_number}")

    # Get repository from environment
    repository = os.environ["GITHUB_REPOSITORY"]

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {os.environ['GH_TOKEN']}",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    base_url = f"https://api.github.com/repos/{repository}/issues"

    # Add label
    try:
        response = requests.post(
            f"{base_url}/{issue_number}/labels",
            headers=headers,
            json={"labels": [label]},
            timeout=30,
        )
        response.raise_for_status()
        print(f"Successfully added label '{label}' to issue #{issue_number}")
    except requests.RequestException as e:
        print(f"Error adding label to issue #{issue_number}: {e}")
        raise

    # Add comment and close issue
    try:
        # Add comment
        response = requests.post(
            f"{base_url}/{issue_number}/comments",
            headers=headers,
            json={"body": message},
            timeout=30,
        )
        response.raise_for_status()
        print(f"Successfully added comment to issue #{issue_number}")

        # Close issue
        response = requests.patch(
            f"{base_url}/{issue_number}",
            headers=headers,
            json={"state": "closed"},
            timeout=30,
        )
        response.raise_for_status()
        print(f"Successfully closed issue #{issue_number}")

    except requests.RequestException as e:
        print(f"Error updating issue #{issue_number}: {e}")
        raise


def get_user_id(username: str) -> Optional[int]:
    """Get GitHub user ID from username with retries on failure.

    Args:
        username: GitHub username to lookup

    Returns:
        The user's GitHub ID if found, None otherwise
    """
    MAX_RETRIES = 3
    RETRY_DELAY = 5  # seconds

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(
                f"https://api.github.com/users/{username}",
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {os.environ['GH_TOKEN']}",
                },
                timeout=30,
            )
            if response.status_code == 200:
                return response.json().get("id")
            elif response.status_code == 404:
                return None
            # Handle rate limiting
            elif (
                response.status_code == 403
                and "X-RateLimit-Remaining" in response.headers
            ):
                if int(response.headers["X-RateLimit-Remaining"]) == 0:
                    reset_time = int(response.headers["X-RateLimit-Reset"])
                    sleep_time = max(reset_time - time.time(), 0)
                    time.sleep(sleep_time)
                    continue
            # Altri status code indicano problemi con l'API, quindi continuiamo a riprovare

        except requests.ReadTimeout:
            continue
        except requests.ConnectionError:
            time.sleep(RETRY_DELAY)
            continue

    return None  # Tutti i tentativi falliti


def get_data_to_store(
    issue_title: str,
    issue_body: str,
    created_at: str,
    had_primary_source: str,
    user_id: int,
) -> dict:
    """Get structured data from issue content for storage.

    Args:
        issue_title: Title of the GitHub issue
        issue_body: Body content of the GitHub issue
        created_at: ISO timestamp when issue was created
        had_primary_source: URL of the original issue
        user_id: GitHub user ID of issue author

    Returns:
        Dictionary containing structured issue data and provenance information

    Raises:
        ValueError: If issue body cannot be split or CSV data is invalid
    """
    try:
        # Split and clean the data sections
        metadata_csv, citations_csv = [
            section.strip() for section in issue_body.split("===###===@@@===")
        ]

        metadata = list(csv.DictReader(io.StringIO(metadata_csv)))
        citations = list(csv.DictReader(io.StringIO(citations_csv)))

        # Validate required data
        if not metadata or not citations:
            raise ValueError("Empty metadata or citations section")

        return {
            "data": {
                "title": issue_title,
                "metadata": metadata,
                "citations": citations,
            },
            "provenance": {
                "generatedAtTime": created_at,
                "wasAttributedTo": f"https://api.github.com/user/{user_id}",
                "hadPrimarySource": had_primary_source,
            },
        }
    except Exception as e:
        raise ValueError(f"Failed to process issue data: {str(e)}")


def _get_zenodo_token() -> str:
    """Get the appropriate Zenodo token based on environment."""
    return get_zenodo_token()


def _create_deposition_resource(
    date: str, base_url: str = "https://zenodo.org/api"
) -> Tuple[str, str]:
    """Create a new deposition resource on Zenodo."""
    metadata = {
        "upload_type": "dataset",
        "publication_date": date,
        "title": f"OpenCitations crowdsourcing: deposits of {date[:7]}",
        "creators": [
            {
                "name": "crocibot",
                "affiliation": "Research Centre for Open Scholarly Metadata, Department of Classical Philology and Italian Studies, University of Bologna, Bologna, Italy",
            }
        ],
        "description": f"OpenCitations collects citation data and related metadata from the community through issues on the GitHub repository <a href='https://github.com/opencitations/crowdsourcing'>https://github.com/opencitations/crowdsourcing</a>. In order to preserve long-term provenance information, such data is uploaded to Zenodo every month. This upload contains the data of deposit issues published in {date[:7]}.",
        "access_right": "open",
        "license": "CC0-1.0",
        "prereserve_doi": True,
        "keywords": [
            "OpenCitations",
            "crowdsourcing",
            "provenance",
            "GitHub issues",
        ],
        "related_identifiers": [
            {
                "identifier": "https://github.com/opencitations/crowdsourcing",
                "relation": "isDerivedFrom",
                "resource_type": "dataset",
            }
        ],
        "version": "1.0.0",
    }
    return create_deposition_resource(date, metadata, base_url)


def _upload_data(
    date: str, bucket: str, base_url: str = "https://zenodo.org/api"
) -> None:
    """Upload data file to Zenodo bucket."""
    filename = f"{date}_weekly_deposit.json"

    with open("data_to_store.json", "rb") as fp:
        response = requests.put(
            f"{bucket}/{filename}",
            data=fp,
            params={"access_token": _get_zenodo_token()},
            timeout=30,
        )
        response.raise_for_status()


def deposit_on_zenodo(data_to_store: List[dict]) -> None:
    """Deposit data on Zenodo based on environment."""
    environment = os.environ.get("ENVIRONMENT", "development")

    # In development, usa la Zenodo Sandbox
    if environment == "development":
        base_url = "https://sandbox.zenodo.org/api"
    else:
        base_url = "https://zenodo.org/api"

    try:
        # Salva i dati in un file temporaneo
        with open("data_to_store.json", "w") as f:
            json.dump(data_to_store, f)

        # Crea una nuova deposizione
        deposition_id, bucket = _create_deposition_resource(
            datetime.now().strftime("%Y-%m-%d"), base_url=base_url
        )

        # Carica i dati
        _upload_data(datetime.now().strftime("%Y-%m-%d"), bucket, base_url=base_url)

        # Pubblica la deposizione
        response = requests.post(
            f"{base_url}/deposit/depositions/{deposition_id}/actions/publish",
            params={"access_token": _get_zenodo_token()},
            timeout=30,
        )

        if response.status_code != 202:
            raise Exception(f"Failed to publish deposition: {response.text}")

    finally:
        # Pulisci i file temporanei
        if os.path.exists("data_to_store.json"):
            os.remove("data_to_store.json")


def is_in_safe_list(user_id: int) -> bool:
    """Check if a user ID is in the safe list.

    Args:
        user_id: GitHub user ID to check

    Returns:
        bool: True if user is in safe list, False otherwise
    """
    try:
        with open(SAFE_LIST_PATH, "r") as f:
            safe_list = yaml.safe_load(f)
            # Extract just the IDs for comparison
            allowed_ids = {str(user["id"]) for user in safe_list.get("users", [])}
            return str(user_id) in allowed_ids
    except FileNotFoundError:
        print("Warning: safe_list.yaml not found, creating empty file")
        # Create empty safe list file with proper structure
        with open(SAFE_LIST_PATH, "w") as f:
            yaml.dump({"users": []}, f)
        return False
    except yaml.YAMLError as e:
        print(f"Error parsing safe_list.yaml: {e}")
        return False


def get_open_issues() -> List[dict]:
    """Fetch open issues with 'deposit' label using GitHub REST API."""
    print("Attempting to fetch open issues...")

    # Get repository info from GitHub Actions environment
    repository = os.environ["GITHUB_REPOSITORY"]
    print(f"Checking repository: {repository}")

    MAX_RETRIES = 3
    RETRY_DELAY = 5

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {os.environ['GH_TOKEN']}",
    }

    for attempt in range(MAX_RETRIES):
        try:
            print(f"Attempt {attempt + 1} of {MAX_RETRIES}")
            response = requests.get(
                f"https://api.github.com/repos/{repository}/issues",
                params={
                    "state": "open",
                    "labels": "deposit",
                },
                headers=headers,
                timeout=30,
            )

            print(f"Response status code: {response.status_code}")

            if response.status_code == 200:
                issues = response.json()
                print(f"Found {len(issues)} issues")
                return [
                    {
                        "title": issue["title"],
                        "body": issue["body"],
                        "number": str(issue["number"]),
                        "author": {"login": issue["user"]["login"]},
                        "createdAt": issue["created_at"],
                        "url": issue["html_url"],
                    }
                    for issue in issues
                ]

            elif response.status_code == 404:
                print("Repository or endpoint not found (404)")
                return []

            elif (
                response.status_code == 403
                and "X-RateLimit-Remaining" in response.headers
            ):
                print(
                    f"Rate limit info: {response.headers.get('X-RateLimit-Remaining')} requests remaining"
                )
                if int(response.headers["X-RateLimit-Remaining"]) == 0:
                    reset_time = int(response.headers["X-RateLimit-Reset"])
                    current_time = time.time()
                    if reset_time > current_time:
                        sleep_time = reset_time - current_time
                        print(f"Rate limit exceeded. Waiting {sleep_time} seconds")
                        time.sleep(sleep_time)
                        continue
                    continue
            else:
                print(f"Unexpected status code: {response.status_code}")
                print(f"Response body: {response.text}")

        except (requests.RequestException, KeyError) as e:
            print(f"Error during request: {str(e)}")
            if attempt < MAX_RETRIES - 1:
                print(f"Waiting {RETRY_DELAY} seconds before retry")
                time.sleep(RETRY_DELAY)
                continue
            raise RuntimeError(
                f"Failed to fetch issues after {MAX_RETRIES} attempts"
            ) from e

    return []


def process_open_issues() -> None:
    """Process all open issues."""

    try:
        print("Starting to process open issues")
        issues = get_open_issues()
        print(f"Found {len(issues)} open issues to process")

        data_to_store = list()

        for issue in issues:
            issue_number = issue["number"]
            print(f"Processing issue #{issue_number}")

            username = issue["author"]["login"]
            print(f"Getting user ID for {username}")
            user_id = get_user_id(username)
            print(f"User ID for {username}: {user_id}")

            if not is_in_safe_list(user_id):
                print(f"WARNING: User {username} (ID: {user_id}) not in safe list")
                answer(
                    False,
                    "To make a deposit, please contact OpenCitations at <contact@opencitations.net> to register as a trusted user",
                    issue_number,
                    is_authorized=False,
                )
                continue

            print(f"User {username} is authorized")
            issue_title = issue["title"]
            issue_body = issue["body"]
            created_at = issue["createdAt"]
            had_primary_source = issue["url"]

            print(f"Validating issue #{issue_number}")
            is_valid, message = validate(issue_title, issue_body, issue_number)
            print(
                f"Validation result for #{issue_number}: valid={is_valid}, message={message}"
            )

            answer(is_valid, message, issue_number, is_authorized=True)
            print(f"Posted answer to issue #{issue_number}")

            if is_valid:
                print(f"Getting data to store for issue #{issue_number}")
                try:
                    issue_data = get_data_to_store(
                        issue_title, issue_body, created_at, had_primary_source, user_id
                    )
                    data_to_store.append(issue_data)
                    print(f"Successfully processed data for issue #{issue_number}")
                except Exception as e:
                    print(f"ERROR: Processing data for issue #{issue_number}: {e}")
                    continue

        if data_to_store:
            print(f"Attempting to deposit {len(data_to_store)} items to Zenodo")
            try:
                deposit_on_zenodo(data_to_store)
                print("Successfully deposited data to Zenodo")
            except Exception as e:
                print(f"ERROR: Failed to deposit data to Zenodo: {e}")
                raise
        else:
            print("No valid data to deposit to Zenodo")

    except Exception as e:
        print(f"ERROR: Processing issues: {e}")
        raise
    finally:
        print("Completed processing open issues")


if __name__ == "__main__":  # pragma: no cover
    process_open_issues()
