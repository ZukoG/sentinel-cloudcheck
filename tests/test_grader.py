import pytest

from grader import grade_headers

GOOD_HEADERS = {
"Strict-Transport-Security": "max-age=31536000; includeSubDomains",
"Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'",
"X-Content-Type-Options": "nosniff",
"X-Frame-Options": "DENY",
"Referrer-Policy": "strict-origin-when-cross-origin",
"Permissions-Policy": "camera=(), microphone=()",
}

def test_all_good_headers_score_100_and_grade_a():
    result = grade_headers(GOOD_HEADERS)


    assert result["score"] == 100
    assert result["grade"] == "A"
    assert all(check["passed"] for check in result["checks"])


def test_missing_headers_score_zero_and_grade_f():
    result = grade_headers({})


    assert result["score"] == 0
    assert result["grade"] == "F"
    assert all(not check["passed"] for check in result["checks"])


def test_header_names_are_case_insensitive():
    mixed_case_headers = {
    name.swapcase(): value
    for name, value in GOOD_HEADERS.items()
    }


    result = grade_headers(mixed_case_headers)

    assert result["score"] == 100
    assert result["grade"] == "A"


@pytest.mark.parametrize(
    ("hsts_value", "expected"),
    [
    ("max-age=100", False),
    ("max-age=15552000", True),
    ("max-age=abc", False),
    ],
)
def test_hsts_max_age_requirement(hsts_value, expected):
    headers = GOOD_HEADERS.copy()
    headers["Strict-Transport-Security"] = hsts_value


    result = grade_headers(headers)

    assert result["checks"][0]["passed"] is expected


def test_csp_frame_ancestors_can_replace_x_frame_options():
    headers = GOOD_HEADERS.copy()
    headers.pop("X-Frame-Options")
    headers["Content-Security-Policy"] = (
    "default-src 'self'; frame-ancestors 'none'"
    )


    result = grade_headers(headers)

    assert result["checks"][3]["passed"] is True


@pytest.mark.parametrize(
    ("policy", "expected"),
    [
    ("unsafe-url, no-referrer", True),
    ("no-referrer, unsafe-url", False),
    ],
)
def test_referrer_policy_uses_last_value(policy, expected):
    headers = GOOD_HEADERS.copy()
    headers["Referrer-Policy"] = policy


    result = grade_headers(headers)

    assert result["checks"][4]["passed"] is expected


@pytest.mark.parametrize(
    "headers",
    [
        {},
        GOOD_HEADERS,
    ],
)
def test_checks_always_contain_six_items_in_the_required_order(headers):
    result = grade_headers(headers)


    expected_headers = [
        "Strict-Transport-Security",
        "Content-Security-Policy",
        "X-Content-Type-Options",
        "X-Frame-Options",
        "Referrer-Policy",
        "Permissions-Policy",
    ]

    assert len(result["checks"]) == 6
    assert [check["header"] for check in result["checks"]] == expected_headers



@pytest.mark.parametrize(
    ("headers_to_remove", "expected_score", "expected_grade"),
    [
        (["Strict-Transport-Security"], 83, "B"),
        (["Strict-Transport-Security", "X-Content-Type-Options"], 67, "C", ),
        (
            [
            "Strict-Transport-Security",
            "X-Content-Type-Options",
            "Referrer-Policy",
            ], 50, "D",
        ),
        (
            [
            "Strict-Transport-Security",
            "X-Content-Type-Options",
            "Referrer-Policy",
            "Permissions-Policy",
            ], 33, "F",
        ),
    ],
)
def test_grade_bands(headers_to_remove, expected_score, expected_grade):
    headers = GOOD_HEADERS.copy()

    
    for header in headers_to_remove:
        headers.pop(header)

    result = grade_headers(headers)

    assert result["score"] == expected_score
    assert result["grade"] == expected_grade
    
