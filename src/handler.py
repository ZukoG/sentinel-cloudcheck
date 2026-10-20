import base64
import binascii
import json
import os
import uuid
import urllib.request
import urllib.error

from datetime import datetime, timezone
from urllib.parse import urlparse

import boto3

from grader import grade_headers


USER_AGENT = "sentinel-cloudcheck/1.0"
FETCH_TIMEOUT_SECONDS = 5


class FetchError(Exception):
    """Raised when the target URL cannot be reached."""


def validate_url(url: str) -> str | None:
    """
    Validate the basic structure of a URL.

    Returns an error message if invalid, or None if valid.
    Private-IP and SSRF checks will be added on Day 3.
    """
    if not isinstance(url, str) or not url.strip():
        return "URL must be a non-empty string"

    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
    except ValueError:
        return "URL is not valid"

    if parsed.scheme not in ("http", "https"):
        return "URL scheme must be http or https"

    if not hostname:
        return "URL must include a hostname"

    return None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Prevent urllib from following redirects."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect())


def fetch_headers(url: str) -> tuple[int, dict[str, str]]:
    """
    Make one GET request and return the response status and headers.

    Redirects are not followed. HTTP error responses such as 404,
    500 and 301 still return their status and headers.
    """
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT},
        method="GET",
    )

    try:
        with _OPENER.open(
            request,
            timeout=FETCH_TIMEOUT_SECONDS,
        ) as response:
            return response.status, dict(response.headers)

    except urllib.error.HTTPError as error:
        # HTTPError is also used for responses such as 301, 404 and 500.
        return error.code, dict(error.headers)

    except (
        urllib.error.URLError,
        TimeoutError,
        OSError,
        ValueError,
    ) as error:
        raise FetchError(str(error)) from error


def save_result(item: dict) -> None:
    """Save a successful scan result to DynamoDB."""
    table_name = os.environ["TABLE_NAME"]

    table = boto3.resource("dynamodb").Table(table_name)
    table.put_item(Item=item)


def _response(status: int, body: dict) -> dict:
    """Build an API Gateway-compatible JSON response."""
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
        },
        "body": json.dumps(body),
    }


def lambda_handler(event, context):
    """Handle a scan request from API Gateway."""

    # 1. Read the request body.
    body = event.get("body") or ""

    try:
        if event.get("isBase64Encoded"):
            body = base64.b64decode(
                body,
                validate=True,
            ).decode("utf-8")

        payload = json.loads(body)

    except (
        json.JSONDecodeError,
        UnicodeDecodeError,
        binascii.Error,
    ):
        return _response(
            400,
            {
                "error": (
                    'Body must be JSON like '
                    '{"url": "https://example.com"}'
                )
            },
        )

    # 2. The JSON body must be an object, not a list or a string.
    if not isinstance(payload, dict):
        return _response(
            400,
            {
                "error": (
                    'Body must be JSON like '
                    '{"url": "https://example.com"}'
                )
            },
        )

    # 3. Validate the requested URL.
    url = payload.get("url")
    
    if isinstance(url, str):
        url = url.strip()
        
    validation_error = validate_url(url)

    if validation_error:
        return _response(
            400,
            {"error": validation_error},
        )

    # 4. Fetch the target's response headers.
    try:
        status_code, headers = fetch_headers(url)

    except FetchError:
        return _response(
            502,
            {"error": f"Could not reach {url}"},
        )

    # 5. Grade the headers.
    result = grade_headers(headers)

    # 6. Build the scan record.
    item = {
        "scan_id": str(uuid.uuid4()),
        "url": url,
        "status_code": status_code,
        "score": result["score"],
        "grade": result["grade"],
        "checks": result["checks"],
        "scanned_at": datetime.now(timezone.utc).isoformat(),
    }

    # 7. Store the successful scan.
    save_result(item)

    # 8. Return the same record to the client.
    return _response(200, item)