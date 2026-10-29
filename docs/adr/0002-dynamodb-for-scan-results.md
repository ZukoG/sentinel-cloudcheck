# ADR 0002: DynamoDB with provisioned capacity for scan results

- **Status:** Accepted
- **Date:** 2026-10-20 (decided while writing the Terraform stack on
  Day 2, written up after v1.0.0)

## Context

Every successful scan has to be stored (FR-5.1). The data and the way it
is used are simple:

- **One small record per scan.** A `scan_id`, the URL, the target's status
  code, the score and grade, the six check results, and a timestamp:
  a few kilobytes at most.
- **Written once, never updated.** The Lambda only ever adds new records.
  Nothing in the project reads records back yet; looking at results
  happens in the AWS console.
- **No relationships.** A scan does not reference any other record, so
  there is nothing to join.
- **The same constraints as the rest of the project:** stay in the free
  tier and leave nothing behind after `terraform destroy` (NFR-3), define
  everything in Terraform (NFR-4), and let the Lambda's IAM role do as
  little as possible (NFR-2).

## Decision

Store scans in a **DynamoDB table** (`sentinel-cloudcheck-scans`) with
`scan_id` as the partition key, using **provisioned capacity of 1 read and
1 write unit** ([`infra/main.tf`](../../infra/main.tf)).

The Lambda writes each scan with a single `PutItem` call, and its IAM role
allows exactly that action on exactly this table and nothing else.

## Alternatives considered

**A relational database on RDS (PostgreSQL or MySQL).** The obvious choice
for a lot of projects, and what sentinel-secscan itself uses. I rejected
it here because nothing in this data is relational, and an RDS instance
is a server: it runs and bills around the clock, needs a VPC and security
groups, and would put the Lambda inside a VPC to reach it, which brings
networking setup and slower cold starts. RDS also has no always-free
allowance, only a time-limited free tier.

**Aurora Serverless.** It can pause its compute when idle, but storage is
still billed, there is no always-free allowance, and it needs the same
VPC networking as RDS. Too much infrastructure for one small table.

**JSON files in S3.** Cheap and simple to write, and a reasonable option.
But S3 is storage for objects, not records: there is no way to look up or
filter scans without listing and downloading files, and the IAM policy
would be about object paths rather than a table. DynamoDB keeps each scan
as a proper, queryable item for almost the same effort. S3 is a better fit
for a future feature like storing PDF reports.

**DynamoDB with on-demand capacity.** The more common setting, because it
needs no capacity planning. But on-demand is billed per request from the
first one, while provisioned capacity up to 25 read and 25 write units is
inside the always-free allowance. One write per second is far more than a
demo needs, so provisioned is free and costs nothing in practice.

## Consequences

**Positive**

- **Free.** 1 read and 1 write unit, a few kilobytes of storage, all
  inside DynamoDB's always-free allowance.
- **No servers and no VPC.** The Lambda reaches DynamoDB through the AWS
  API, so it stays outside any VPC, which also keeps it away from any
  private network (see [ADR 0003](0003-ip-pinned-fetching.md)).
- **Tight permissions.** The role grants `dynamodb:PutItem` on this one
  table. It cannot read, update, delete, or scan anything.
- **Clean teardown.** The table is a Terraform resource, so
  `terraform destroy` removes it along with every stored scan.

**Negative**

- **Limited querying.** Items can be fetched by `scan_id` cheaply, but
  something like "every scan of this URL, newest first" would need a
  secondary index or a full table scan. A scan-history feature would mean
  adding a global secondary index on `url` and `scanned_at`.
- **Provisioned capacity can throttle.** Above 1 write per second,
  DynamoDB starts rejecting writes. The API's own throttle (2 requests per
  second, burst 5) is in front of it, and demo traffic is nowhere near it,
  but a real workload would need higher capacity or on-demand mode.
- **Different from the other projects.** sentinel-secscan uses
  PostgreSQL, so this is a second data model to know. For data this
  simple, that trade-off is worth it.
- **Data does not survive teardown.** Destroying the stack deletes every
  stored scan. That is the intended behaviour for a demo stack, but a
  long-lived deployment would want backups or point-in-time recovery.
