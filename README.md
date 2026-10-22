# sentinel-cloudcheck

[![CI](https://github.com/ZukoG/sentinel-cloudcheck/actions/workflows/ci.yml/badge.svg)](https://github.com/ZukoG/sentinel-cloudcheck/actions/workflows/ci.yml)

A small serverless API on AWS that grades a website's HTTP security
headers. Send it a URL, and an AWS Lambda function fetches that page
once, scores six security headers, stores the result in DynamoDB, and
returns the grade as JSON. The whole stack is defined in Terraform:
one command creates it, one command removes it.

Built for a Cloud Computing elective, as a companion to
[sentinel-secscan](https://github.com/ZukoG/sentinel-secscan).

## Why

Missing security headers are one of the most common, and easiest to
fix, web misconfigurations. This project checks them with a real cloud
deployment end to end: serverless compute, a managed API, a managed
database, least-privilege IAM, infrastructure as code, and CI, all
inside the AWS free tier.

It is passive only: one ordinary GET request per scan, no payloads, no
crawling, no attacks.

## Architecture

```mermaid
flowchart LR
    client([Client]) -- "POST /scan<br/>HTTPS" --> api["API Gateway<br/>HTTP API<br/>(throttled)"]
    api --> lambda["Lambda<br/>Python 3.13"]
    lambda -- "1 GET, pinned to a<br/>checked public IP" --> target([Target website])
    lambda -- "PutItem only" --> db[("DynamoDB<br/>scans table")]
    lambda -. logs .-> cw["CloudWatch Logs<br/>7-day retention"]
```

| Resource | Purpose |
|---|---|
| API Gateway (HTTP API) | Public HTTPS endpoint, one route (`POST /scan`), throttled to 2 req/s, burst 5 |
| Lambda | Validates the URL, fetches the target, grades the headers, stores the result |
| DynamoDB | One item per scan, provisioned at 1 read and 1 write unit (always free) |
| IAM role | Can write only its own logs and `PutItem` into only its own table |
| CloudWatch Logs | Lambda logs, deleted after 7 days and on `terraform destroy` |

All 10 resources live in [`infra/main.tf`](infra/main.tf).

## What it checks

| Header | Passes when |
|---|---|
| `Strict-Transport-Security` | `max-age` is at least 180 days |
| `Content-Security-Policy` | present and not empty |
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` or `SAMEORIGIN`, or the CSP has `frame-ancestors` |
| `Referrer-Policy` | `no-referrer`, `same-origin`, `strict-origin`, or `strict-origin-when-cross-origin` |
| `Permissions-Policy` | present and not empty |

Score is the share of checks passed (0 to 100). Grade: **A** 90+,
**B** 75+, **C** 60+, **D** 40+, **F** below 40. Full rules are in
[SRS section 4](docs/SRS.md#4-functional-requirements).

## Before you start

You need one AWS account and three free programs. This takes about 20
minutes the first time, and you only ever do it once.

| You need | What it is | Cost |
|---|---|---|
| An AWS account | Where the project runs | Free plan, nothing charged |
| Git | Downloads the project | Free |
| AWS CLI | Lets your computer talk to your AWS account | Free |
| Terraform | Builds and removes everything on AWS for you | Free |
| Python (optional) | Only needed to run the tests | Free |

> **About the terminal:** a few steps ask you to type a command. On
> Windows, press the Windows key, type **PowerShell**, and press Enter.
> On macOS, open **Terminal** from Applications, then Utilities. Copy a
> command from this page, paste it into that window, and press Enter.

### Step 1: Create an AWS account

> AWS Skill Builder and AWS Educate logins are **not** AWS accounts.
> They are for courses only and cannot run this project.

1. Go to **https://signin.aws.amazon.com/signup?request_type=register**
2. Enter your email and an account name, then type in the code AWS emails you.
3. Choose a password. This is the **root** login, the master key to the account.
4. If asked to choose a plan, pick **Free plan**.
5. Choose **Personal** and fill in your details.
6. Add a bank card. AWS uses it to check you are a real person. The free plan does not charge it.
7. Confirm your phone number with the code AWS sends.
8. For the support plan, choose **Basic support (free)**.

### Step 2: Protect the account with MFA

MFA means a password alone is not enough to get in.

1. Sign in at **https://console.aws.amazon.com/** as **Root user**.
2. Go to **https://console.aws.amazon.com/iam/home#/security_credentials**
3. Under **Multi-factor authentication (MFA)**, click **Assign MFA device**.
4. Choose **Authenticator app**, then scan the QR code with an app such
   as Google Authenticator or Microsoft Authenticator on your phone.
5. Type in two codes from the app, one after the other, and click **Add MFA**.

### Step 3: Set a zero-spend alert

This emails you if your account is ever charged even 1 cent, so there
are no surprises.

1. Go to **https://console.aws.amazon.com/billing/home#/budgets**
2. Click **Create budget**, then **Use a template**.
3. Pick **Zero spend budget**, enter your email, and click **Create budget**.

### Step 4: Create your own user and access key

The root login should not be used day to day. Create a separate user
for this project.

1. Go to **https://console.aws.amazon.com/iam/home#/users** and click **Create user**.
2. Name it (for example `my-admin`). Leave **console access unticked**. Click **Next**.
3. Choose **Attach policies directly**, tick **AdministratorAccess**, click **Next**, then **Create user**.
4. Click the new user's name, open the **Security credentials** tab, and click **Create access key**.
5. Choose **Command Line Interface (CLI)**, tick the confirmation box, click **Next**, then **Create access key**.
6. Click **Download .csv file** and keep it somewhere safe.

> **Keep that .csv file private.** It holds an *Access Key ID* and a
> *Secret Access Key*, which together work like a password to your AWS
> account. Never paste them into a chat, an email, a screenshot, or any
> file in a project. This project never needs them written down
> anywhere except in step 7 below.

### Step 5: Install Git, the AWS CLI, and Terraform

**Windows:** open PowerShell and run these three commands, one at a time:

```powershell
winget install --id Git.Git -e
winget install --id Amazon.AWSCLI -e
winget install --id Hashicorp.Terraform -e
```

**macOS:** install [Homebrew](https://brew.sh) first if you do not have it, then:

```bash
brew install git awscli hashicorp/tap/terraform
```

**Linux:** install Git from your package manager (for example
`sudo apt install git`), then follow the official guides for the
[AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
and [Terraform](https://developer.hashicorp.com/terraform/install).

If you prefer normal installers, download them from
**https://git-scm.com/downloads**,
**https://awscli.amazonaws.com/AWSCLIV2.msi** (Windows AWS CLI), and
**https://developer.hashicorp.com/terraform/install**.

> **Important:** close the terminal window and open a new one after
> installing. A window that was already open does not know about the
> new programs yet, and will say "not recognized".

### Step 6 (optional): Install Python

Only needed if you want to run the tests. On Windows:

```powershell
winget install --id Python.Python.3.13 -e
```

Or download it from **https://www.python.org/downloads/**. On the first
installer screen, tick **Add python.exe to PATH**.

### Step 7: Connect the AWS CLI to your account

In a new terminal window, run:

```bash
aws configure
```

It asks four questions. Answer each and press Enter:

| Question | What to type |
|---|---|
| AWS Access Key ID | The *Access key ID* from your .csv file |
| AWS Secret Access Key | The *Secret access key* from your .csv file |
| Default region name | `eu-west-1` |
| Default output format | `json` |

Newer versions of the AWS CLI may also ask whether to set up "AWS skills
and the AWS MCP server" for AI coding agents. Type `n`. This project
does not need it.

### Step 8: Check everything works

Run these one at a time. Each should print a version number:

```bash
git --version
aws --version
terraform version
```

Then check that AWS knows who you are:

```bash
aws sts get-caller-identity
```

You should see your 12-digit account number and a line ending in
`user/my-admin` (or whatever you named your user). If you do, you are
ready.

## Quick start

### 1. Deploy

```bash
git clone https://github.com/ZukoG/sentinel-cloudcheck.git
cd sentinel-cloudcheck/infra
terraform init
terraform apply
```

Type `yes` when asked. It takes under a minute and ends with:

```
Apply complete! Resources: 10 added, 0 changed, 0 destroyed.

Outputs:

function_name = "sentinel-cloudcheck-scanner"
scan_url = "https://<api-id>.execute-api.eu-west-1.amazonaws.com/scan"
table_name = "sentinel-cloudcheck-scans"
```

The default region is `eu-west-1`. To use another one, run
`terraform apply -var="aws_region=<region>"`.

### 2. Scan a site

**Windows PowerShell** (in PowerShell, `curl` is a different command,
so use `Invoke-RestMethod`):

```powershell
$url = terraform output -raw scan_url
Invoke-RestMethod -Method Post -Uri $url -ContentType "application/json" -Body '{"url": "https://github.com"}' | ConvertTo-Json -Depth 5
```

**Linux, macOS, or Git Bash:**

```bash
URL=$(terraform output -raw scan_url)
curl -s -X POST "$URL" -H "Content-Type: application/json" -d '{"url": "https://github.com"}'
```

Real response from a live deployment:

```json
{
    "scan_id": "b91fabd3-8b79-449a-bfa6-607314e35de0",
    "url": "https://github.com",
    "status_code": 200,
    "score": 83,
    "grade": "B",
    "checks": [
        {"header": "Strict-Transport-Security", "passed": true, "detail": "max-age=31536000 meets the 180-day minimum"},
        {"header": "Content-Security-Policy", "passed": true, "detail": "Header is present"},
        {"header": "X-Content-Type-Options", "passed": true, "detail": "Value is nosniff"},
        {"header": "X-Frame-Options", "passed": true, "detail": "X-Frame-Options provides framing protection"},
        {"header": "Referrer-Policy", "passed": true, "detail": "Final policy 'strict-origin-when-cross-origin' is accepted"},
        {"header": "Permissions-Policy", "passed": false, "detail": "Header is missing or empty"}
    ],
    "scanned_at": "2026-10-22T05:03:57.783295+00:00"
}
```

Errors come back as JSON too. Also captured from the live deployment:

| Request `url` | Status | Response |
|---|---|---|
| `http://169.254.169.254/latest/meta-data/` | 400 | `{"error": "URL must point to a public address"}` |
| `ftp://example.com` | 400 | `{"error": "URL scheme must be http or https"}` |
| `https://does-not-exist.invalid` | 502 | `{"error": "Unable to reach target"}` |

Only successful scans are stored. The DynamoDB table after the scans
above:

```
+-------+--------+-------------------------------+
| grade | score  |              url              |
+-------+--------+-------------------------------+
|  B    |  83    |  https://github.com           |
|  A    |  100   |  https://www.cloudflare.com   |
+-------+--------+-------------------------------+
```

### 3. See it in the AWS console

Make sure the region selector (top right) matches the deployed region,
**Europe (Ireland)** by default, or everything will look empty.

- **DynamoDB**, then Explore items, then `sentinel-cloudcheck-scans`: one item per scan
- **Lambda**, then `sentinel-cloudcheck-scanner`: the function and its Monitor tab
- **CloudWatch**, then Log groups, then `/aws/lambda/sentinel-cloudcheck-scanner`: one log stream per run
- **API Gateway**, then `sentinel-cloudcheck-api`: the route and throttling settings

### 4. Tear it down

```bash
terraform destroy
```

Type `yes`. It ends with `Destroy complete! Resources: 10 destroyed.`
and removes everything, logs included. To double-check nothing is
left, `terraform state list` should print nothing. More ways to verify
are in [Security and Cost](docs/SECURITY_AND_COST.md#6-teardown).

## Running the tests

The 49 unit tests need no AWS account and no internet: DNS, fetching,
and DynamoDB are all faked, plus one local HTTP server.

```bash
python -m venv .venv
.venv\Scripts\activate        # PowerShell; Git Bash: source .venv/Scripts/activate; Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -v
```

CI runs the same tests on Python 3.13, plus `terraform fmt -check` and
`terraform validate`, on every pull request. CI never needs AWS
credentials.

## Security

A service that fetches any URL a stranger sends it can be abused to
reach things inside the cloud provider (server-side request forgery,
SSRF). This one defends in layers:

- Only `http`/`https`, at most 2048 characters.
- The hostname is resolved first, and rejected if **any** address is
  private, loopback, link-local (including the `169.254.169.254` cloud
  metadata address), or otherwise non-public. This also catches tricks
  like `http://2130706433/` or a public name pointing at `127.0.0.1`.
- The fetch connects to the exact IP that was checked, so a hostile DNS
  server cannot swap in a private address afterwards (DNS rebinding).
  TLS certificates are still fully verified against the hostname.
- Redirects are never followed.
- The Lambda's IAM role can do two things only: write its own logs and
  `PutItem` into its own table.

Details, including what was tested against the live API, are in
[docs/SECURITY_AND_COST.md](docs/SECURITY_AND_COST.md).

## Cost

Every resource sits inside the AWS free tier at demo scale, and
`terraform destroy` removes all of it. A per-service breakdown is in
[docs/SECURITY_AND_COST.md](docs/SECURITY_AND_COST.md#5-cost-nfr-3).

## Project structure

```
src/
  grader.py        pure grading logic, no network or AWS
  handler.py       Lambda entry point: validate, resolve, fetch, grade, store
tests/
  test_grader.py
  test_handler.py
infra/
  main.tf          all AWS resources
  variables.tf     region, name prefix, log retention, throttling
  outputs.tf       scan_url, table_name, function_name
docs/
  SRS.md                 requirements
  SECURITY_AND_COST.md   IAM, SSRF defences, throttling, cost, teardown
.github/workflows/ci.yml tests and Terraform checks
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `terraform` or `aws` is "not recognized" right after installing | Close and reopen the terminal so it picks up the new PATH |
| `pip install` fails on Windows with a long path error | Clone into a shorter folder (for example `C:\Users\<you>\Desktop`). botocore's data files have very long names |
| The AWS console shows nothing | Switch the region selector to the deployed region (Europe (Ireland) by default) |
| `429 Too Many Requests` or `503` | You hit the API throttle or the account's Lambda concurrency limit. Wait a second and retry |

## Documentation

- [Software Requirements Specification](docs/SRS.md)
- [Security and Cost](docs/SECURITY_AND_COST.md)

## License

[MIT](LICENSE)
