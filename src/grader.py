# HSTS requirement
HSTS_MIN_AGE = 15552000

# Accepted Referrer-Policy values
ACCEPTED_REFERRER_POLICIES = {
    'no-referrer',
    'same-origin',
    'strict-origin',
    'strict-origin-when-cross-origin',
}

KNOWN_REFERRER_POLICIES = {
    'no-referrer',
    'no-referrer-when-downgrade',
    'origin',
    'origin-when-cross-origin',
    'same-origin',
    'strict-origin',
    'strict-origin-when-cross-origin',
    'unsafe-url',
}

# Minimum scores for each grade
GRADE_A_MIN = 90
GRADE_B_MIN = 75
GRADE_C_MIN = 60
GRADE_D_MIN = 40

def _result(header: str, passed: bool, detail: str) -> dict:
    return {
    "header": header,
    "passed": passed,
    "detail": detail,
}


def _check_hsts(headers: dict[str, str]) -> dict:
    value = headers.get('strict-transport-security')
    
    if value is None:
        return _result(
            'Strict-Transport-Security',
            False,
            'Header is missing',
        )
        
    max_age = None
    
    for directive in value.split(';'):
        name, _, value = directive.partition("=")

        if name.strip().lower() == "max-age":
            max_age_text = value.strip()

            if (
                len(max_age_text) >= 2
                and max_age_text.startswith('"')
                and max_age_text.endswith('"')
            ):
                max_age_text = max_age_text[1:-1]

            try:
                max_age = int(max_age_text)
            except ValueError:
                max_age = None
                break
    
    if max_age is None:
        return _result(
            'Strict-Transport-Security',
            False,
            'Missing or invalid max-age',
        )
        
    if max_age < HSTS_MIN_AGE:
        return _result(
            'Strict-Transport-Security',
            False,
            f'max-age={max_age} is below the 180-day minimum',
        )
        
    return _result(
        'Strict-Transport-Security',
        True,
        f'max-age={max_age} meets the 180-day minimum',
    )
    
    
def _check_csp(headers: dict[str, str]) -> dict:
    value = headers.get('content-security-policy')
        
    if not value:
        return _result(
            'Content-Security-Policy',
            False,
            'Header is missing or empty',
        )
            
    return _result(
        'Content-Security-Policy',
        True,
        'Header is present',
    )
    

def _check_content_type_options(headers: dict[str, str]) -> dict:
    value = headers.get('x-content-type-options')
    
    if value is None or value.lower() != 'nosniff':
        return _result(
            'X-Content-Type-Options',
            False,
            'Expected value: nosniff',
        )
    
    return _result(
        "X-Content-Type-Options",
        True,
        "Value is nosniff",
    )

def _check_frame_options(headers: dict[str, str]) -> dict:
    value = headers.get('x-frame-options', '')
    csp = headers.get('content-security-policy', '')
    
    if value.upper() in {'DENY', 'SAMEORIGIN'}:
        return _result(
            "X-Frame-Options",
            True,
            "X-Frame-Options provides framing protection",
        )
    
    if "frame-ancestors" in csp.lower():
        return _result(
            "X-Frame-Options",
            True,
            "CSP frame-ancestors provides framing protection",
        )

    return _result(
        "X-Frame-Options",
        False,
        "Expected DENY, SAMEORIGIN, or a CSP frame-ancestors directive",
    )

def _check_referrer_policy(headers: dict[str, str]) -> dict:
    value = headers.get("referrer-policy")

    if value is None or not value:
        return _result(
            "Referrer-Policy",
            False,
            "Header is missing or empty",
        )

    recognised_policies = [
        token.strip().lower()
        for token in value.split(",")
        if token.strip().lower() in KNOWN_REFERRER_POLICIES
    ]

    if not recognised_policies:
        return _result(
            "Referrer-Policy",
            False,
            "No recognised policy",
        )

    final_policy = recognised_policies[-1]

    if final_policy in ACCEPTED_REFERRER_POLICIES:
        return _result(
            "Referrer-Policy",
            True,
            f"Final policy '{final_policy}' is accepted",
        )

    return _result(
        "Referrer-Policy",
        False,
        f"Final policy '{final_policy}' is not accepted",
    )
    
def _check_permissions_policy(headers: dict[str, str]) -> dict:
    value = headers.get("permissions-policy")

    if value is None or not value:
        return _result(
            "Permissions-Policy",
            False,
            "Header is missing or empty",
        )

    return _result(
        "Permissions-Policy",
        True,
        "Header is present",
    )

def grade_headers(headers: dict[str, str]) -> dict:
    normalised_headers = {
        name.lower(): value.strip()
        for name, value in headers.items()
    }

    checks = [
        _check_hsts(normalised_headers),
        _check_csp(normalised_headers),
        _check_content_type_options(normalised_headers),
        _check_frame_options(normalised_headers),
        _check_referrer_policy(normalised_headers),
        _check_permissions_policy(normalised_headers),
    ]

    passed_count = sum(
        check["passed"]
        for check in checks
    )

    score = round(passed_count / 6 * 100)

    if score >= GRADE_A_MIN:
        grade = "A"
    elif score >= GRADE_B_MIN:
        grade = "B"
    elif score >= GRADE_C_MIN:
        grade = "C"
    elif score >= GRADE_D_MIN:
        grade = "D"
    else:
        grade = "F"

    return {
        "score": score,
        "grade": grade,
        "checks": checks,
    }