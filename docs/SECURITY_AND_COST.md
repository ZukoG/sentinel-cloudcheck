# Security and Cost

How sentinel-cloudcheck limits what it can do, what it costs to run, and
how to make sure nothing is left running afterwards. Requirement numbers
refer to [SRS.md](SRS.md).

## 1. IAM: least privilege (NFR-2)

The Lambda function runs as its own IAM role,
`sentinel-cloudcheck-scanner-role`, with one inline policy defined in
[`infra/main.tf`](../infra/main.tf):

| Statement | Actions | Resource |
|---|---|---|
| `WriteOwnLogs` | `logs:CreateLogStream`, `logs:PutLogEvents` | Its own log group only |
| `PutScanResults` | `dynamodb:PutItem` | Its own table only |

Nothing else is allowed. The function cannot read, update, delete, or
scan the table, cannot touch any other table or log group, and cannot
call any other AWS service. If the code were ever compromised, the worst
it could do is write extra items into its own table.

I deliberately did not attach the AWS managed policy
`AWSLambdaBasicExecutionRole`. It is the usual default, but it allows
`logs:CreateLogGroup` and log writes on every resource (`*`). Creating
the log group in Terraform instead means the role only needs access to
that one group.

Only API Gateway can invoke the function: the `aws_lambda_permission`
resource is scoped to this API's own ARN.

## 2. Network: fetching user-supplied URLs safely

A service that fetches any URL a stranger sends it is a classic
server-side request forgery (SSRF) risk: the request comes from inside
the cloud provider, so it might reach things the stranger cannot.
Defences, in layers:

| Layer | What it stops | Where |
|---|---|---|
| Scheme and host check | `ftp://`, `file://`, URLs with no host | FR-2.1 |
| Length limit (2048) | Oversized input | FR-2.2 |
| Public-address-only resolution | `127.0.0.1`, private ranges, `169.254.169.254` (cloud metadata), IPv6 equivalents, encoded forms like `http://2130706433/` | FR-2.3 |
| Redirects never followed | A public URL that redirects to an internal one | FR-3.3 |
| Connection pinned to the checked IP | DNS rebinding: a hostile DNS server answering with a public address for the check, then a private one for the fetch | FR-3.4 |
| Full TLS verification | A pinned connection to the wrong server: the certificate must still match the hostname | FR-3.4 |
| Lambda outside any VPC | There is no private network attached to reach | `infra/main.tf` |
| One GET, 5 second timeout | Using the scanner to hammer a target | FR-3.1, NFR-1 |

Error responses never echo internal details: a blocked destination
returns only "URL must point to a public address", without the address
it resolved to, and an unreachable one returns only "Unable to reach
target".

## 3. Abuse limits (NFR-7)

The API has no login (accepted risk, SRS section 6). To stop anyone who
finds the URL from running up invocations, the API Gateway stage is
throttled to 2 requests per second with a burst of 5
(`throttle_rate_limit` / `throttle_burst_limit` in
[`infra/variables.tf`](../infra/variables.tf)). Requests above that get
`429 Too Many Requests` from API Gateway and never reach Lambda.

API Gateway throttling is best-effort rather than an exact counter, so
a second limit backs it up: a new AWS account can run at most 10 Lambda
executions at the same time, and anything beyond that is rejected with
`503`. Measured against the live stack, 60 requests fired from 40
parallel threads came back as 36 normal responses, 4 `429` (API Gateway
throttle), and 20 `503` (Lambda concurrency limit). Either way, a flood
of requests cannot turn into an unbounded number of invocations.

## 4. Secrets (NFR-5)

- No credentials exist anywhere in the repo. Terraform and the AWS CLI
  read them from the local AWS CLI profile.
- `*.tfstate` and `*.tfvars` are gitignored. State can contain resource
  details, and variable files are where secrets usually end up.
- CI never talks to AWS. `terraform validate` runs with
  `-backend=false`, so the workflow needs no AWS secrets at all.
- The CI workflow's GitHub token is read-only (`permissions: contents: read`).

## 5. Cost (NFR-3)

Every resource fits in the AWS free tier at demo scale:

| Service | Used for | Always-free allowance | This project's usage |
|---|---|---|---|
| Lambda | The scanner | 1M requests and 400,000 GB-seconds per month | A few requests, 128 MB, about a second each |
| DynamoDB | Scan results | 25 GB storage, 25 provisioned read and 25 write units | 1 read and 1 write unit, a few KB |
| CloudWatch Logs | Lambda logs | 5 GB ingestion per month | A few KB, deleted after 7 days |
| API Gateway (HTTP API) | Public endpoint | Free tier for new accounts | A handful of requests |
| IAM | Role and policy | Always free | 1 role, 1 policy |

The DynamoDB table uses provisioned capacity (1 read, 1 write unit)
rather than on-demand. Provisioned units sit inside the always-free
allowance, while on-demand is billed per request from the first one.

Recommended safety net for any account running this: a zero-spend AWS
Budget (Billing, then Budgets, then the "Zero spend budget" template),
which sends an email if any charge at all appears.

## 6. Teardown

The stack is meant to exist only while it is being used. To remove it:

```bash
cd infra
terraform destroy
```

It should end with `Destroy complete! Resources: 10 destroyed.` Two
quick ways to confirm nothing is left. Terraform's own record should be
empty (prints nothing):

```bash
terraform state list
```

And every resource carries a `Project = sentinel-cloudcheck` tag, so a
tag search should print `0`:

```bash
aws resourcegroupstaggingapi get-resources --tag-filters Key=Project,Values=sentinel-cloudcheck --query "length(ResourceTagMappingList)"
```

`terraform destroy` also removes the logs, because the log group is
managed by Terraform rather than created automatically by Lambda.
