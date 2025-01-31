#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright 2022 Arcangelo Massari <arcangelo.massari@unibo.it>
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
import logging
import os
import time
from typing import List

import requests
import yaml
from oc_meta.run.meta_process import run_meta_process
from SPARQLWrapper import JSON, SPARQLWrapper


logger = logging.getLogger(__name__)


def dump_csv(data_to_store: List[dict], output_path: str):
    keys = data_to_store[0].keys()
    with open(output_path, "w", newline="") as output_file:
        dict_writer = csv.DictWriter(output_file, keys)
        dict_writer.writeheader()
        dict_writer.writerows(data_to_store)


def check_triplestore_connection(endpoint_url: str) -> bool:
    """Check if the triplestore is responsive with a simple SPARQL query.

    Args:
        endpoint_url: The URL of the SPARQL endpoint

    Returns:
        bool: True if the triplestore is responsive, False otherwise
    """
    try:
        sparql = SPARQLWrapper(endpoint_url)
        sparql.setQuery("SELECT ?s WHERE { ?s ?p ?o } LIMIT 1")
        sparql.setReturnFormat(JSON)
        sparql.query()
        return True
    except Exception as e:
        logger.error(f"Error connecting to triplestore at {endpoint_url}: {str(e)}")
        return False


def get_ingestion_dirs() -> tuple[str, str, str]:
    """Create and return paths for ingestion directories.

    Creates a directory structure like:
    crowdsourcing_ingestion_data/
    └── YYYY_MM/
        ├── metadata/
        └── citations/

    Returns:
        tuple containing:
        - base_dir: Path to the main ingestion directory for this month
        - metadata_dir: Path to metadata directory
        - citations_dir: Path to citations directory
    """
    current_date = time.strftime("%Y_%m")
    base_dir = os.path.join("crowdsourcing_ingestion_data", current_date)
    metadata_dir = os.path.join(base_dir, "metadata")
    citations_dir = os.path.join(base_dir, "citations")

    # Create directory structure
    os.makedirs(metadata_dir, exist_ok=True)
    os.makedirs(citations_dir, exist_ok=True)

    return base_dir, metadata_dir, citations_dir


def store_meta_input(issues: List[dict]) -> None:
    """Store metadata and citations from issues into CSV files.

    This function:
    1. Creates directory structure for current month's ingestion
    2. Extracts metadata and citations from each issue's body
    3. Stores data in CSV files, with a maximum of 1000 records per file

    Args:
        issues: List of issue dictionaries containing body and number

    Raises:
        ValueError: If an issue's body doesn't contain the expected separator
        IOError: If there are issues creating directories or writing files
    """
    _, metadata_dir, citations_dir = get_ingestion_dirs()
    metadata_to_store = []
    citations_to_store = []
    metadata_counter = 0
    citations_counter = 0

    for issue in issues:
        try:
            issue_body = issue["body"]
            if "===###===@@@===" not in issue_body:
                logger.warning(
                    f"Warning: Issue #{issue['number']} does not contain the expected separator"
                )
                continue

            # Split metadata and citations sections
            metadata_section, citations_section = [
                section.strip() for section in issue_body.split("===###===@@@===")
            ]

            if not metadata_section:
                logger.warning(
                    f"Warning: Issue #{issue['number']} has empty metadata section"
                )
                continue

            if not citations_section:
                logger.warning(
                    f"Warning: Issue #{issue['number']} has empty citations section"
                )
                continue

            # Process metadata
            metadata = list(csv.DictReader(io.StringIO(metadata_section)))
            if not metadata:
                logger.warning(
                    f"Warning: Issue #{issue['number']} has no valid metadata records"
                )
                continue

            # Process citations
            citations = list(csv.DictReader(io.StringIO(citations_section)))
            if not citations:
                logger.warning(
                    f"Warning: Issue #{issue['number']} has no valid citation records"
                )
                continue

            # Only extend the lists if both metadata and citations are valid
            metadata_to_store.extend(metadata)
            citations_to_store.extend(citations)

            # Write metadata to file when we reach 1000 records
            while len(metadata_to_store) >= 1000:
                dump_csv(
                    metadata_to_store[:1000],
                    os.path.join(metadata_dir, f"{metadata_counter}.csv"),
                )
                metadata_to_store = metadata_to_store[1000:]
                metadata_counter += 1

            # Write citations to file when we reach 1000 records
            while len(citations_to_store) >= 1000:
                dump_csv(
                    citations_to_store[:1000],
                    os.path.join(citations_dir, f"{citations_counter}.csv"),
                )
                citations_to_store = citations_to_store[1000:]
                citations_counter += 1

        except (KeyError, csv.Error) as e:
            logger.error(
                f"Error processing issue #{issue.get('number', 'unknown')}: {str(e)}"
            )
            continue

    # Write any remaining records
    if metadata_to_store:
        dump_csv(
            metadata_to_store, os.path.join(metadata_dir, f"{metadata_counter}.csv")
        )
    if citations_to_store:
        dump_csv(
            citations_to_store,
            os.path.join(citations_dir, f"{citations_counter}.csv"),
        )


def get_closed_issues() -> List[dict]:
    """Fetch closed issues with 'to be processed' label using GitHub REST API."""
    MAX_RETRIES = 3
    RETRY_DELAY = 5

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {os.environ['GH_TOKEN']}",
    }

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(
                f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}/issues",
                params={
                    "state": "closed",
                    "labels": "to be processed",
                },
                headers=headers,
                timeout=30,
            )

            if response.status_code == 200:
                issues = response.json()
                logger.info(f"Found {len(issues)} issues")
                return [
                    {
                        "body": issue["body"],
                        "number": str(issue["number"]),
                        "user": {
                            "login": issue["user"]["login"],
                            "html_url": issue["user"]["html_url"],
                            "id": issue["user"]["id"],
                        },
                    }
                    for issue in issues
                ]

            elif response.status_code == 404:
                logger.error("Repository or endpoint not found (404)")
                return []

            elif (
                response.status_code == 403
                and "X-RateLimit-Remaining" in response.headers
            ):
                logger.info(
                    f"Rate limit info: {response.headers.get('X-RateLimit-Remaining')} requests remaining"
                )
                if int(response.headers["X-RateLimit-Remaining"]) == 0:
                    reset_time = int(response.headers["X-RateLimit-Reset"])
                    current_time = time.time()
                    if reset_time > current_time:
                        sleep_time = reset_time - current_time
                        logger.info(
                            f"Rate limit exceeded. Waiting {sleep_time} seconds"
                        )
                        time.sleep(sleep_time)
                        continue
                    continue
            else:
                logger.error(f"Unexpected status code: {response.status_code}")
                logger.error(f"Response body: {response.text}")

        except (requests.RequestException, KeyError) as e:
            logger.error(f"Error during request: {str(e)}")
            if attempt < MAX_RETRIES - 1:
                logger.info(f"Waiting {RETRY_DELAY} seconds before retry")
                time.sleep(RETRY_DELAY)
                continue
            raise RuntimeError(
                f"Failed to fetch issues after {MAX_RETRIES} attempts"
            ) from e

    return []


def process_single_issue(issue: dict, base_settings: dict) -> bool:
    """Process a single issue, updating meta configuration with issue URI as source.

    Args:
        issue: Dictionary containing issue data
        base_settings: Base meta configuration settings

    Returns:
        bool: True if processing was successful, False otherwise
    """
    # Store metadata and citations for this issue
    store_meta_input([issue])

    # Get paths for current ingestion
    base_dir, metadata_dir, citations_dir = get_ingestion_dirs()

    # Create issue-specific settings with issue URI as source and GitHub user as resp_agent
    issue_settings = base_settings.copy()
    issue_number = str(issue["number"])
    issue_settings.update(
        {
            "input_csv_dir": metadata_dir,
            "source": f"https://github.com/{os.environ['GITHUB_REPOSITORY']}/issues/{issue_number}",
            "resp_agent": f"https://api.github.com/user/{issue['user']['id']}",
        }
    )

    # Create temporary config file with issue-specific settings
    temp_config_path = os.path.join(base_dir, f"meta_config_{issue_number}.yaml")
    with open(temp_config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(issue_settings, f)

    # Run meta processing for this issue
    try:
        run_meta_process(
            settings=issue_settings,
            meta_config_path=temp_config_path,
            resp_agents_only=False,
        )
        return True
    except Exception as e:
        logger.error(f"Error processing issue #{issue_number}: {str(e)}")
        return False
    finally:
        # Clean up temporary config
        if os.path.exists(temp_config_path):
            os.remove(temp_config_path)


def update_issue_labels(issue_number: str, success: bool) -> None:
    """Update issue labels based on processing result using GitHub REST API.

    Args:
        issue_number: The issue number to update
        success: Whether the processing was successful
    """
    logger.info(f"Updating labels for issue #{issue_number} (success={success})")

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {os.environ['GH_TOKEN']}",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    base_url = f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}/issues/{issue_number}"
    logger.info(f"Using API URL: {base_url}")

    try:
        # Remove 'to be processed' label
        logger.info("Attempting to remove 'to be processed' label")
        response = requests.delete(
            f"{base_url}/labels/to%20be%20processed",
            headers=headers,
            timeout=30,
        )
        logger.info(f"Delete label response status: {response.status_code}")
        if response.status_code != 200:
            logger.error(f"Error response from delete label: {response.text}")

        # Add appropriate label based on success
        new_label = "done" if success else "oc meta error"
        logger.info(f"Attempting to add new label: {new_label}")
        response = requests.post(
            f"{base_url}/labels",
            headers=headers,
            json={"labels": [new_label]},
            timeout=30,
        )
        logger.info(f"Add label response status: {response.status_code}")
        if response.status_code not in [200, 201]:  # Both are valid success codes
            logger.error(f"Error adding label: {response.text}")
        else:
            logger.info(
                f"Successfully added label '{new_label}' to issue #{issue_number}"
            )

    except requests.RequestException as e:
        logger.error(f"Error updating labels for issue {issue_number}: {e}")
        raise


def process_meta_issues() -> None:
    """Process closed issues with 'to be processed' label for meta data extraction.

    This function:
    1. Checks triplestore connection
    2. Fetches closed issues with 'to be processed' label
    3. Processes each issue individually:
       - Updates meta configuration with issue URI as source
       - Processes metadata and citations
       - Runs meta processing pipeline
    4. Updates issue labels based on processing results
    """

    try:
        # Load base meta configuration
        with open("meta_config.yaml", encoding="utf-8") as f:
            base_settings = yaml.safe_load(f)

        # Check triplestore connection first
        if not check_triplestore_connection(base_settings["triplestore_url"]):
            logger.error("Triplestore is not responsive, aborting process")
            return

        issues = get_closed_issues()

        if not issues:
            logger.info("No issues to process")
            return

        # Process each issue individually
        for issue in issues:
            issue_number = str(issue["number"])
            logger.info(f"\nProcessing issue #{issue_number}")

            success = process_single_issue(issue, base_settings)
            update_issue_labels(issue_number, success)

    except Exception as e:
        logger.error(f"Error in process_meta_issues: {str(e)}", exc_info=True)
        raise


if __name__ == "__main__":  # pragma: no cover
    process_meta_issues()
