import base64
import json

import pytest

import handler
import threading

from http.server import BaseHTTPRequestHandler, HTTPServer


def _event(body):
    """Build a basic API Gateway request event."""
    return {
        "body": json.dumps(body),
    }


@pytest.fixture
def saved_items(monkeypatch):
    """Replace DynamoDB saving with an in-memory list."""
    items = []

    def fake_save_result(item):
        items.append(item.copy())

    monkeypatch.setattr(handler, "save_result", fake_save_result)

    return items


@pytest.fixture
def successful_fetch(monkeypatch):
    """Simulate a website returning secure HTTP headers."""

    headers = {
        "Strict-Transport-Security": "max-age=31536000",
        "Content-Security-Policy": "default-src 'self'",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "camera=(), microphone=()",
    }

    def fake_fetch(url):
        return 200, headers

    monkeypatch.setattr(handler, "fetch_headers", fake_fetch)

    return headers


def test_valid_scan_returns_200_and_saves_result(
    saved_items,
    successful_fetch,
):
    response = handler.lambda_handler(
        _event({"url": "https://example.com"}),
        None,
    )

    assert response["statusCode"] == 200

    body = json.loads(response["body"])

    expected_fields = {
        "scan_id",
        "url",
        "status_code",
        "score",
        "grade",
        "checks",
        "scanned_at",
    }

    assert expected_fields.issubset(body.keys())

    assert body["url"] == "https://example.com"
    assert body["status_code"] == 200

    assert len(saved_items) == 1
    assert saved_items[0]["scan_id"] == body["scan_id"]
    assert saved_items[0] == body


@pytest.mark.parametrize(
    "body",
    [
        "not valid JSON",
        '["a"]',
        "{}",
        '{"url": "ftp://example.com"}',
        '{"url": "https://"}',
        '{"url": ""}',
        '{"url": 123}',
        '{"url": "http://[::1"}',
    ],
)
def test_invalid_requests_return_400_without_saving(
    body,
    saved_items,
):
    response = handler.lambda_handler(
        {"body": body},
        None,
    )

    assert response["statusCode"] == 400
    assert len(saved_items) == 0


def test_unreachable_target_returns_502_without_saving(
    monkeypatch,
    saved_items,
):
    def fake_fetch(url):
        raise handler.FetchError("Connection timed out")

    monkeypatch.setattr(handler, "fetch_headers", fake_fetch)

    response = handler.lambda_handler(
        _event({"url": "https://unreachable.example"}),
        None,
    )

    assert response["statusCode"] == 502
    assert json.loads(response["body"]) == {
        "error": "Could not reach https://unreachable.example"
    }

    assert len(saved_items) == 0


def test_base64_encoded_request_is_supported(
    saved_items,
    successful_fetch,
):
    original_body = json.dumps(
        {"url": "https://example.com"}
    ).encode("utf-8")

    encoded_body = base64.b64encode(original_body).decode("utf-8")

    event = {
        "body": encoded_body,
        "isBase64Encoded": True,
    }

    response = handler.lambda_handler(event, None)

    assert response["statusCode"] == 200
    assert len(saved_items) == 1


def test_target_redirect_is_graded_without_being_followed(
    monkeypatch,
    saved_items,
):
    def fake_fetch(url):
        return 301, {
            "Location": "https://another.example",
            "Content-Security-Policy": "default-src 'self'",
        }

    monkeypatch.setattr(handler, "fetch_headers", fake_fetch)

    response = handler.lambda_handler(
        _event({"url": "https://example.com"}),
        None,
    )

    assert response["statusCode"] == 200

    body = json.loads(response["body"])

    assert body["status_code"] == 301
    assert len(saved_items) == 1
    assert saved_items[0]["status_code"] == 301
    
    
    
def test_url_whitespace_is_removed_before_saving(
    saved_items,
    successful_fetch,
):
    response = handler.lambda_handler(
        _event({"url": "  https://example.com  "}),
        None,
    )

    assert response["statusCode"] == 200

    body = json.loads(response["body"])

    assert body["url"] == "https://example.com"
    assert saved_items[0]["url"] == "https://example.com"
    
    

class _RedirectServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(301)
        self.send_header(
            "Location",
            "http://127.0.0.1:1/never",
        )
        self.end_headers()

    def log_message(self, *args):
        pass


def test_fetch_headers_does_not_follow_redirects():
    server = HTTPServer(
        ("127.0.0.1", 0),
        _RedirectServer,
    )

    thread = threading.Thread(
        target=server.serve_forever,
        daemon=True,
    )

    thread.start()

    try:
        url = f"http://127.0.0.1:{server.server_port}/"

        status_code, headers = handler.fetch_headers(url)

        assert status_code == 301
        assert "Location" in headers
        assert headers["Location"] == "http://127.0.0.1:1/never"

    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)