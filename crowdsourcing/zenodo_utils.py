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
    """Create a new deposition resource on Zenodo."""
    headers = {"Content-Type": "application/json"}

    if base_url is None:
        base_url = get_zenodo_base_url()

    response = requests.post(
        f"{base_url}/deposit/depositions",
        params={"access_token": get_zenodo_token()},
        json={"metadata": metadata},
        headers=headers,
        timeout=30,
    )

    response.raise_for_status()
    data = response.json()

    return data["id"], data["links"]["bucket"]
