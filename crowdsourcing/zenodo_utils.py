# SPDX-FileCopyrightText: 2025 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

import os
from typing import Tuple

import requests


def get_zenodo_token() -> str:
    """Get the appropriate Zenodo token based on environment."""
    environment = os.environ.get("ENVIRONMENT", "development")
    if environment == "development":
        token = os.environ.get("ZENODO_SANDBOX")
        if not token:
            raise ValueError("ZENODO_SANDBOX token not found in environment")
        return token
    else:
        token = os.environ.get("ZENODO_PRODUCTION")
        if not token:
            raise ValueError("ZENODO_PRODUCTION token not found in environment")
        return token


def get_zenodo_base_url() -> str:
    """Get the appropriate Zenodo API base URL based on environment."""
    environment = os.environ.get("ENVIRONMENT", "development")
    return (
        "https://sandbox.zenodo.org/api"
        if environment == "development"
        else "https://zenodo.org/api"
    )


def create_deposition_resource(
    date: str, metadata: dict, base_url: str = None
) -> Tuple[str, str]:
    """Create a new deposition resource on Zenodo.

    Args:
        date: The publication date in ISO format (YYYY-MM-DD)
        metadata: The metadata for the deposition (will be wrapped in {"metadata": metadata})
        base_url: The Zenodo API base URL (optional, defaults to environment-based URL)

    Returns:
        Tuple containing:
        - str: The deposition ID
        - str: The bucket URL for file uploads
    """
    headers = {"Content-Type": "application/json"}

    # Zenodo API expects metadata wrapped in a "metadata" key
    payload = {"metadata": metadata}

    response = requests.post(
        f"{base_url}/deposit/depositions",
        params={"access_token": get_zenodo_token()},
        json=payload,
        headers=headers,
        timeout=30,
    )

    response.raise_for_status()
    data = response.json()

    return data["id"], data["links"]["bucket"]
