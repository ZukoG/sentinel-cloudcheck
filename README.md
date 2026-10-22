# sentinel-cloudcheck

[![CI](https://github.com/ZukoG/sentinel-cloudcheck/actions/workflows/ci.yml/badge.svg)](https://github.com/ZukoG/sentinel-cloudcheck/actions/workflows/ci.yml)

A small serverless API on AWS that grades a website's HTTP security
headers. Send it a URL, and an AWS Lambda function fetches that page
once, scores six security headers, stores the result in DynamoDB, and
returns the grade as JSON. The whole stack is defined in Terraform:
one command creates it, one command removes it.

Built for a Cloud Computing elective, as a companion to
[sentinel-secscan](https://github.com/ZukoG/sentinel-secscan).

## Table of contents

- 💡 [Why](#why)
- 🏗️ [Architecture](#architecture)
- 🔍 [What it checks](#what-it-checks)
- 🧰 [Before you start](#before-you-start)
  - 👤 [Step 1: Create an AWS account](#step-1-create-an-aws-account)
  - 🔐 [Step 2: Protect the account with MFA](#step-2-protect-the-account-with-mfa)
  - 💰 [Step 3: Set a zero-spend alert](#step-3-set-a-zero-spend-alert)
  - 🔑 [Step 4: Create your own user and access key](#step-4-create-your-own-user-and-access-key)
  - 📦 [Step 5: Install Git, the AWS CLI, and Terraform](#step-5-install-git-the-aws-cli-and-terraform)
  - 🐍 [Step 6 (optional): Install Python](#step-6-optional-install-python)
  - 🔗 [Step 7: Connect the AWS CLI to your account](#step-7-connect-the-aws-cli-to-your-account)
  - ✅ [Step 8: Check everything works](#step-8-check-everything-works)
- 🚀 [How to run it](#how-to-run-it)
  - ⬇️ [Step 1: Download the project](#step-1-download-the-project)
  - 📂 [Step 2: Go into the project's infra folder](#step-2-go-into-the-projects-infra-folder)
  - ⚙️ [Step 3: Prepare Terraform](#step-3-prepare-terraform-first-time-only)
  - ☁️ [Step 4: Build it on AWS](#step-4-build-it-on-aws)
  - 🌐 [Step 5: Scan a website](#step-5-scan-a-website)
  - 👀 [Step 6: See it in the AWS console](#step-6-see-it-in-the-aws-console)
  - 🧹 [Step 7: Remove everything when you are done](#step-7-remove-everything-when-you-are-done)
- 🧪 [Running the tests](#running-the-tests)
- 🛡️ [Security](#security)
- 💵 [Cost](#cost)
- 🗂️ [Project structure](#project-structure)
- 🩺 [Troubleshooting](#troubleshooting)
- 📚 [Documentation](#documentation)
- 📄 [License](#license)

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

## How to run it

Finished [Before you start](#before-you-start)? Then this takes about 5
minutes. Every step says what you should see, so you always know it
worked.

### Step 1: Download the project

In a terminal, run:

```bash
git clone https://github.com/ZukoG/sentinel-cloudcheck.git
```

You should see `Cloning into 'sentinel-cloudcheck'...`. This makes a
`sentinel-cloudcheck` folder inside whichever folder your terminal is
in (usually your user folder).

> **No Git?** On this project's GitHub page, click the green **Code**
> button, then **Download ZIP**, and extract it. The folder will be
> called `sentinel-cloudcheck-main` instead, so use that name in step 2.

### Step 2: Go into the project's `infra` folder

```bash
cd sentinel-cloudcheck/infra
```

`cd` means "change directory", which moves the terminal into that
folder. The `infra` folder holds the files describing everything that
gets built on AWS.

### Step 3: Prepare Terraform (first time only)

```bash
terraform init
```

Terraform downloads the small add-ons it needs to talk to AWS. You
should see, in green:

```
Terraform has been successfully initialized!
```

### Step 4: Build it on AWS

```bash
terraform apply
```

Terraform shows a long list of the 10 things it is about to create,
then asks:

```
Do you want to perform these actions?
  Enter a value:
```

Type `yes` and press Enter. Under a minute later you should see:

```
Apply complete! Resources: 10 added, 0 changed, 0 destroyed.

Outputs:

function_name = "sentinel-cloudcheck-scanner"
scan_url = "https://<api-id>.execute-api.eu-west-1.amazonaws.com/scan"
table_name = "sentinel-cloudcheck-scans"
```

That `scan_url` is your live API on the internet. The project is now
running.

> Want a different AWS region than Ireland (`eu-west-1`)? Use
> `terraform apply -var="aws_region=<region>"` instead.

### Step 5: Scan a website

Stay in the same terminal (still inside `infra`), and copy the block for
your system. To scan a different site, change `https://github.com` to
any website address.

**Windows (PowerShell):**

```powershell
$url = terraform output -raw scan_url
Invoke-RestMethod -Method Post -Uri $url -ContentType "application/json" -Body '{"url": "https://github.com"}' | ConvertTo-Json -Depth 5
```

> In PowerShell, `curl` is a different command, which is why this uses
> `Invoke-RestMethod` instead.

**macOS, Linux, or Git Bash:**

```bash
URL=$(terraform output -raw scan_url)
curl -s -X POST "$URL" -H "Content-Type: application/json" -d '{"url": "https://github.com"}'
```

You should get back the site's grade. This is a real response from a
live deployment:

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

How to read it: `grade` is the overall result (A is best, F is worst),
`score` is out of 100, and each entry in `checks` says whether one
security header passed and why. GitHub got a B because it is missing
only `Permissions-Policy`.

Bad requests get a clear error instead. These were also captured from
the live deployment:

| If you send | You get | Why |
|---|---|---|
| `http://169.254.169.254/latest/meta-data/` | 400 `{"error": "URL must point to a public address"}` | Internal cloud addresses are blocked |
| `ftp://example.com` | 400 `{"error": "URL scheme must be http or https"}` | Only website addresses are accepted |
| `https://does-not-exist.invalid` | 502 `{"error": "Unable to reach target"}` | The site does not exist |

### Step 6: See it in the AWS console

1. Sign in at **https://console.aws.amazon.com/** (your own user or root both work).
2. **Check the region** in the top-right corner says **Europe (Ireland)**.
   If it shows another region, click it and choose Europe (Ireland),
   otherwise everything will look empty.
3. Type the service name into the search bar at the top:
   - **DynamoDB**, then **Explore items**, then `sentinel-cloudcheck-scans`: every scan you ran is stored here
   - **Lambda**, then `sentinel-cloudcheck-scanner`: the code that does the scanning
   - **CloudWatch**, then **Log groups**, then `/aws/lambda/sentinel-cloudcheck-scanner`: a log of every run
   - **API Gateway**, then `sentinel-cloudcheck-api`: the public address and its rate limit

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

### Step 7: Remove everything when you are done

**Do not skip this.** Back in the terminal, still inside `infra`:

```bash
terraform destroy
```

Type `yes` when asked. You should see:

```
Destroy complete! Resources: 10 destroyed.
```

Everything the project created on AWS is now gone, logs and stored scans
included, so nothing keeps running. To bring it back any time, just
repeat steps 4 to 6 (you get a new `scan_url` each time).

To double-check nothing is left, this should print nothing at all:

```bash
terraform state list
```

More ways to verify are in [Security and Cost](docs/SECURITY_AND_COST.md#6-teardown).

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
| `terraform apply` says `No valid credential sources found` | The AWS CLI is not connected yet. Redo [Step 7](#step-7-connect-the-aws-cli-to-your-account) of Before you start |
| `terraform output` says no outputs found | You are not in the `infra` folder, or nothing is deployed. `cd` into `infra` and run `terraform apply` |
| The AWS console shows nothing | Switch the region selector to the deployed region (Europe (Ireland) by default) |
| `429 Too Many Requests` or `503` | You hit the API throttle or the account's Lambda concurrency limit. Wait a second and retry |

## Documentation

- [Software Requirements Specification](docs/SRS.md)
- [Security and Cost](docs/SECURITY_AND_COST.md)

## License

[MIT](LICENSE)
