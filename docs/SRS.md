# Software Requirements Specification: sentinel-cloudcheck

Version 0.4.0

## 1. Purpose

sentinel-cloudcheck is a serverless API on AWS that grades a website's
HTTP security headers. It exists to show a small, real cloud deployment
end to end: managed compute (Lambda), a managed API front door (API
Gateway), a managed database (DynamoDB), least-privilege IAM, and
infrastructure as code (Terraform), all within the AWS free tier.

## 2. Scope

### In scope
- One HTTP endpoint that accepts a URL and returns a security header grade.
- A single GET request to the target URL per scan.
- Storing each scan result in DynamoDB.
- Creating and destroying the full AWS stack with Terraform.

### Out of scope
- Any active or offensive testing: no payloads, no fuzzing, no port
  scanning, no crawling beyond the one requested page. Passive only, the
  same rule as sentinel-secscan.
- User accounts and authentication on the API (see section 6).
- A web frontend.
- Endpoints for listing or deleting past scans.
- Scheduled or recurring scans.

## 3. Architecture

```
client --HTTPS--> API Gateway (HTTP API) --> Lambda (Python) --GET--> target site
                                               |
                                               +--PutItem--> DynamoDB table
```

Lambda runs outside any VPC, so it has no route into a private network.
That alone does not stop it from reaching public cloud metadata or
loopback-style addresses, which is why FR-2.3 exists.

## 4. Functional Requirements

### FR-1: Request
- FR-1.1: The API accepts `POST /scan` with a JSON body `{"url": "<target>"}`.

### FR-2: Input validation
- FR-2.1: The URL must use `http` or `https` and include a host. Anything
  else returns 400 with an error message.
- FR-2.2: URLs longer than 2048 characters return 400.
- FR-2.3: The hostname is resolved before fetching, and **every** address
  it resolves to must be a public (globally routable) address. If any
  address is private, loopback, link-local (including the
  `169.254.169.254` cloud metadata address), carrier-grade NAT,
  unspecified, reserved, or multicast, the API returns 400. IPv4-mapped
  IPv6 addresses (`::ffff:127.0.0.1`) are checked as the IPv4 address
  they contain. This also covers IP literals and unusual encodings such
  as `http://2130706433/`: either they resolve to a blocked address
  (400), or they do not resolve at all (502). Neither is fetched.
- FR-2.4: If the hostname cannot be resolved at all, the API returns 502
  (the target cannot be reached, same as FR-3.2), and nothing is stored.

### FR-3: Fetch
- FR-3.1: The Lambda sends exactly one GET request to the target, with a
  5 second timeout and a fixed `User-Agent` identifying the tool.
- FR-3.2: If the target cannot be reached, the API returns 502 with an
  error message, and nothing is stored. A 4xx or 5xx response from the
  target still counts as reached, since it still has headers to grade.
- FR-3.3: Redirects are not followed. If the target answers with a 3xx,
  that redirect response's own headers are graded. Following redirects
  would mean sending requests to a URL the user never submitted, which
  would let a redirect bypass the destination checks in FR-2.3. The
  response includes the target's status code so a redirect is visible.
- FR-3.4: The fetch connects to the exact IP address that FR-2.3 checked,
  without resolving the hostname a second time. The hostname is still
  sent in the `Host` header and as the TLS server name, and the TLS
  certificate is still fully verified against it. This closes DNS
  rebinding, where a hostile DNS server answers with a public address
  for the check and a private one for the fetch.

### FR-4: Grading
Each of the six checks below passes or fails. Header names are matched
case-insensitively.

| # | Header | Passes when |
|---|---|---|
| 1 | `Strict-Transport-Security` | present and `max-age` is at least 15552000 (180 days) |
| 2 | `Content-Security-Policy` | present and not empty |
| 3 | `X-Content-Type-Options` | value is `nosniff` |
| 4 | `X-Frame-Options` | value is `DENY` or `SAMEORIGIN`, or the CSP contains a `frame-ancestors` directive |
| 5 | `Referrer-Policy` | value is one of `no-referrer`, `same-origin`, `strict-origin`, `strict-origin-when-cross-origin` (if several comma-separated values are given, the last one counts, as in browsers) |
| 6 | `Permissions-Policy` | present and not empty |

- FR-4.1: Score = passed checks / 6 x 100, rounded to the nearest whole number.
- FR-4.2: Grade bands: A at 90 or above, B at 75 or above, C at 60 or
  above, D at 40 or above, F below 40.
- FR-4.3: Each check reports the header name, whether it passed, and a
  short human-readable detail explaining why.

### FR-5: Storage
- FR-5.1: Every successful scan is written to DynamoDB with: `scan_id`
  (UUID, partition key), `url`, `status_code`, `score`, `grade`, `checks`, `scanned_at`
  (UTC, ISO 8601).

### FR-6: Response
- FR-6.1: A successful scan returns 200 with `scan_id`, `url`,
  `status_code` (the target's HTTP status), `score`, `grade`, `checks`,
  and `scanned_at` as JSON. `status_code` is also stored (FR-5.1).

## 5. Non-Functional Requirements

- NFR-1 Passive only: one GET per scan, no request body, no attack payloads.
- NFR-2 Least privilege: the Lambda's IAM role can write logs and call
  `dynamodb:PutItem` on its own table, nothing else.
- NFR-3 Cost: every resource stays within the AWS free tier, and
  `terraform destroy` removes everything the project created.
- NFR-4 Reproducible: the whole stack is defined in Terraform, nothing is
  created by hand in the console.
- NFR-5 No secrets in the repo: AWS credentials stay in the local AWS CLI
  profile, Terraform state and variable files are gitignored.
- NFR-6 Testable offline: unit tests run without network access or an AWS
  account.
- NFR-7 Abuse limits: API Gateway throttling caps request rate, so a
  public endpoint cannot be used to run up Lambda invocations.

## 6. Accepted Risks

- The API has no authentication. Anyone with the endpoint URL can request
  a scan. This is acceptable for a short-lived demo stack that is
  destroyed after use, and NFR-7 limits the damage. A long-lived
  deployment would need an API key or JWT authorizer.

## 7. Open Questions

None yet.
