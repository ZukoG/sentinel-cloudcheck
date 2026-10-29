# ADR 0003: Pin the fetch to the already-checked IP address

- **Status:** Accepted
- **Date:** 2026-10-21 (decided while hardening input validation on
  Day 3, written up after v1.0.0)

## Context

The scanner fetches whatever URL a stranger sends it. Without care, that
is server-side request forgery (SSRF): someone could ask it to fetch
`http://169.254.169.254/` (the cloud metadata address), `127.0.0.1`, or a
private network address, and the request would come from inside AWS.

[FR-2.3](../SRS.md) already resolves the hostname first and rejects it if
**any** address it resolves to is not public. But a plain fetch resolves
the hostname a **second** time when it connects. That gap is DNS
rebinding: an attacker who controls a domain's DNS can answer the check
with a public address, then answer the fetch a moment later with a
private one. The check passes, and the request still goes somewhere it
must not.

Version 0.3.0 of the SRS recorded this as an accepted risk. The question
was whether to close it.

## Decision

The fetch connects to the **exact IP address that was checked**, and
never resolves the hostname again ([FR-3.4](../SRS.md)).

`check_destination()` resolves the hostname, rejects it if any address is
non-public, and returns a verified address. `fetch_headers()` then opens a
socket straight to that IP through small subclasses of Python's
`http.client.HTTPConnection` and `HTTPSConnection`
([`src/handler.py`](../../src/handler.py)). The original hostname is still
sent in the `Host` header, and for HTTPS it is passed as the TLS server
name, so the certificate is still fully verified against the hostname the
user asked for.

## Alternatives considered

**A plain fetch, re-resolving on connect.** The simplest code: call
`urllib` with the URL. It leaves the rebinding window open. I rejected it
because the check is only as good as the guarantee that the request goes
where the check looked.

**Keep DNS rebinding as an accepted risk.** Defensible here, and the
original plan. Lambda runs outside any VPC, so there is no private network
behind it, and redirects are never followed (FR-3.3). But the metadata
address and loopback still exist inside Lambda's environment, and the fix
turned out to be small, so leaving a known gap open was not worth it.

**Connect to the IP and skip TLS verification.** Connecting to an IP while
verifying the certificate needs the hostname passed through separately.
Turning verification off would make pinning trivial, but then any server
at that IP could pretend to be the requested site. Rejected outright.

**An outbound proxy or egress firewall** that blocks private ranges at the
network level. The strongest option for a large system, and the right one
when many services make outbound requests. For one function it means a
VPC, a proxy or NAT setup, and running costs, all far beyond the size of
this project.

## Consequences

**Positive**

- **Closes DNS rebinding.** The address that passed the check is the only
  address the request can reach.
- **TLS still verified.** A pinned connection to a server with a bad
  certificate fails. `https://expired.badssl.com/` returned `502` on the
  live deployment, and `https://wrong.host.badssl.com/` (a certificate for
  a different hostname) did the same in local testing.
- **Proven against the live API.** The metadata address (IPv4 and IPv6),
  loopback, private ranges, `localtest.me`, and encoded forms like
  `http://2130706433/` all return `400`
  ([SECURITY_AND_COST.md](../SECURITY_AND_COST.md#2-network-fetching-user-supplied-urls-safely)).
- **Testable offline.** The redirect test serves from a local server
  under the unresolvable hostname `redirect-test.invalid`. It can only
  pass if the fetch really connects to the pinned IP without resolving.

**Negative**

- **More code to own.** About 120 lines of custom connection handling
  replaced a one-line `urllib` call, and they sit on `http.client`
  internals such as the `_context` attribute of `HTTPSConnection`, which
  could change in a future Python version. CI on Python 3.13 catches that
  before it ships.
- **Only the first verified address is tried.** If a site's first address
  is unreachable from Lambda, for example an IPv6 address, the scan
  returns `502` instead of falling back to the next one. It has not
  happened against real sites so far, and falling back to each verified
  address in turn would be a contained change.
- **No redirect following, ever.** Pinning makes following a redirect
  safely much harder, since each new hop would need its own check and pin.
  The scanner already grades the redirect response itself (FR-3.3), so
  this costs nothing today.
