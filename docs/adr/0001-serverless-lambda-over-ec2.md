# ADR 0001: Serverless Lambda over EC2 for the scanner

- **Status:** Accepted
- **Date:** 2026-10-19 (decided while planning the project, written up
  after v1.0.0)

## Context

sentinel-cloudcheck needs somewhere to run the code that takes a URL,
fetches it once, grades its headers, and stores the result. Whatever I
picked had to fit a few constraints from the [SRS](../SRS.md):

- **Short, occasional work.** One scan is a single GET with a 5 second
  timeout (FR-3.1). Measured on the live deployment, a full scan took
  about 0.6 seconds and a rejected request about 2 to 30 milliseconds.
  Demo traffic is a handful of requests a day, with long stretches of
  nothing.
- **Free tier, and nothing left running (NFR-3).** The project has to cost
  nothing, and `terraform destroy` has to remove everything it created.
- **Everything as code (NFR-4).** The compute has to be created and
  destroyed by Terraform alongside everything else.
- **A small attack surface.** The service fetches URLs that strangers send
  it, so the less there is to secure and patch, the better.

## Decision

Run the scanner as an **AWS Lambda function** (Python 3.13, 128 MB,
10 second timeout), invoked by an **API Gateway HTTP API** with a single
`POST /scan` route. Both are defined in [`infra/main.tf`](../../infra/main.tf).

Lambda runs the code only when a request arrives and is billed per
invocation and per millisecond of run time. API Gateway provides the
public HTTPS endpoint, routing, and throttling, so the project contains no
web server code at all.

## Alternatives considered

**An EC2 instance running a small web server.** The traditional choice,
and the most flexible: any language, any framework, no time limit per
request. I rejected it because it fits this workload badly. It would sit
running and billing around the clock to do well under a second of work a
few times a day. I would own the operating system: patching it, hardening
it, and securing SSH access to a machine whose whole job is fetching
untrusted URLs. Scaling would mean adding an Auto Scaling group and a
load balancer, and the free tier's EC2 allowance is time-limited rather
than always free.

**Containers on ECS with Fargate.** No servers to patch, and a better fit
than EC2 for longer-running services. But it needs a container image, a
registry, a cluster, a task definition, a service, and usually a load
balancer, all to run one short function. That is a lot of extra
infrastructure, and cost, for no benefit at this scale.

**App Runner or Elastic Beanstalk.** Both hide much of that setup, but
both are built around keeping an application running, and neither has an
always-free allowance that covers an idle service.

**Running it on my own machine and exposing it.** Free, but it isn't a
cloud deployment, it needs my laptop to be on, and it would mean opening
a port on a home network to arbitrary traffic. That defeats the point of
the project.

## Consequences

**Positive**

- **Pay per use.** Idle time costs nothing, and demo traffic sits far
  inside Lambda's always-free allowance of 1 million requests and 400,000
  GB-seconds a month.
- **No servers to manage.** AWS patches the runtime and the operating
  system. There is no SSH, no open port, and no machine to harden, which
  matters for a service that fetches untrusted URLs.
- **Scales on its own,** and the account's concurrency limit (10 on a new
  account) caps how far it can scale, which doubles as a cost guard. This
  was measured: 60 concurrent requests produced 20 `503` responses once
  the limit was reached ([SECURITY_AND_COST.md](../SECURITY_AND_COST.md#3-abuse-limits-nfr-7)).
- **Clean teardown.** The function, its role, its log group, and the API
  are all Terraform resources, so `terraform destroy` removes all ten
  resources with nothing left behind.
- **Least privilege is easy to express.** The function runs as its own IAM
  role allowed to write its own logs and `PutItem` into its own table,
  and nothing else.

**Negative**

- **Cold starts.** The first request after a quiet period waits while AWS
  starts a fresh environment. For a demo API that is a short, acceptable
  delay, but it rules this design out for anything with strict latency
  requirements.
- **Limits that a server would not have.** A run can last at most 15
  minutes, and the request and response size is capped. Neither matters
  for a single sub-second fetch, but a feature like crawling a whole site
  would need a different design.
- **Different runtime, different behaviour.** Code that passes locally
  can still fail on Lambda. The deployed function crashed with a `500` on
  unresolvable hostnames, because the Lambda runtime raises a plain
  `OSError` where Windows raises `socket.gaierror`. It was only found by
  testing the live deployment and reading CloudWatch Logs
  ([#8](https://github.com/ZukoG/sentinel-cloudcheck/issues/8)).
- **Tied to AWS.** The handler's event and response shape, and the IAM and
  API Gateway setup, are specific to AWS. The grading logic is not:
  `grader.py` is plain Python with no AWS code, so it would move to
  another platform unchanged.
