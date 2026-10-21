import base64
import binascii
import json
import os
import uuid
import ipaddress
import socket
import http.client
import ssl

from datetime import datetime, timezone
from urllib.parse import urlparse

import boto3

from grader import grade_headers


USER_AGENT = "sentinel-cloudcheck/1.0"
FETCH_TIMEOUT_SECONDS = 5
MAX_URL_LENGTH = 2048


class FetchError(Exception):
    """Raised when the target URL cannot be reached."""


class DestinationError(Exception):
    """Raised when the target resolves to a non-public address."""


def validate_url(url: str) -> str | None:
    """
    Validate the basic structure and length of a URL.

    Returns an error message if invalid, or None if valid.
    Destination IP checks happen separately in check_destination().
    """
    if not isinstance(url, str) or not url.strip():
        return "URL must be a non-empty string"

    if len(url) > MAX_URL_LENGTH:
        return f"URL must be at most {MAX_URL_LENGTH} characters"

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


def _is_public_address(address: str) -> bool:
    """Return whether an IP address is suitable as a public destination."""
    ip = ipaddress.ip_address(address)

    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped

    return ip.is_global and not ip.is_multicast


def check_destination(hostname: str) -> str:
    """
    Resolve a hostname and return a validated public IP address.

    Raises DestinationError if any resolved address is not public.
    DNS resolution failures raise FetchError.
    """
    try:
        infos = socket.getaddrinfo(
            hostname,
            None,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
    except socket.gaierror as error:
        raise FetchError(str(error)) from error

    if not infos:
        raise FetchError("Hostname did not resolve to an IP address")

    addresses = []

    for info in infos:
        address = info[4][0]

        try:
            is_public = _is_public_address(address)
        except ValueError:
            is_public = False

        if not is_public:
            raise DestinationError("URL must point to a public address")

        if address not in addresses:
            addresses.append(address)

    # The hostname has been checked, and all returned addresses are public.
    return addresses[0]



def _open_pinned_socket(
    address: str,
    port: int,
    timeout: float,
    ) -> socket.socket:
    """Connect directly to an IP address without resolving its hostname."""
    ip = ipaddress.ip_address(address)


    family = socket.AF_INET6 if ip.version == 6 else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.settimeout(timeout)

    try:
        if ip.version == 6:
            sock.connect((str(ip), port, 0, 0))
        else:
            sock.connect((str(ip), port))
        return sock
    except Exception:
        sock.close()
        raise


class _PinnedHTTPConnection(http.client.HTTPConnection):
    """HTTP connection that uses a previously validated IP address."""

    def __init__(
        self,
        hostname: str,
        port: int,
        address: str,
        timeout: float,
    ):
        super().__init__(hostname, port, timeout=timeout)
        self._validated_address = address

    def connect(self):
        self.sock = _open_pinned_socket(
            self._validated_address,
            self.port,
            self.timeout,
        )


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection pinned to an IP while preserving TLS verification."""

    def __init__(
        self,
        hostname: str,
        port: int,
        address: str,
        timeout: float,
    ):
        super().__init__(
            hostname,
            port,
            timeout=timeout,
            context=ssl.create_default_context(),
        )
        self._validated_address = address

    def connect(self):
            raw_socket = _open_pinned_socket(
                self._validated_address,
                self.port,
                self.timeout,
            )

            try:
                self.sock = self._context.wrap_socket(
                    raw_socket,
                    server_hostname=self.host,
                )
            except Exception:
                raw_socket.close()
                raise




def fetch_headers(
    url: str,
    validated_ip: str,
    ) -> tuple[int, dict[str, str]]:
    """
    Fetch HTTP headers using a previously validated IP address.

    ```
    Redirects are not followed. HTTP responses such as 301, 404 and
    500 are returned normally with their status codes and headers.
    """
    parsed = urlparse(url)
    hostname = parsed.hostname

    if hostname is None:
        raise FetchError("URL must contain a hostname")

    try:
        port = parsed.port
        if port is None:
            port = 443 if parsed.scheme == "https" else 80

        if parsed.scheme == "https":
            connection = _PinnedHTTPSConnection(
                hostname,
                port,
                validated_ip,
                FETCH_TIMEOUT_SECONDS,
            )
        elif parsed.scheme == "http":
            connection = _PinnedHTTPConnection(
                hostname,
                port,
                validated_ip,
                FETCH_TIMEOUT_SECONDS,
            )
        else:
            raise FetchError("Unsupported URL scheme")

        host_header = f"[{hostname}]" if ":" in hostname else hostname

        default_port = 443 if parsed.scheme == "https" else 80
        if port != default_port:
            host_header = f"{host_header}:{port}"

        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        try:
            connection.request(
                "GET",
                path,
                headers={
                    "User-Agent": USER_AGENT,
                    "Host": host_header,
                },
            )

            response = connection.getresponse()

            return response.status, dict(response.headers)

        finally:
            connection.close()

    except FetchError:
        raise
    except (
        http.client.HTTPException,
        OSError,
        TimeoutError,
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

    # 4. Check that the destination resolves only to public addresses.
    try:
        hostname = urlparse(url).hostname

        if hostname is None:
            return _response(
                400,
                {"error": "URL must contain a hostname"},
            )

        validated_ip = check_destination(hostname)

    except DestinationError as error:
        return _response(400, {"error": str(error)})

    except FetchError:
        return _response(502, {"error": "Unable to reach target"})

    try:
        status_code, headers = fetch_headers(url, validated_ip)

    except FetchError:
        return _response(502, {"error": "Unable to reach target"})

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