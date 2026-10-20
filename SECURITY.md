# Security policy

## Supported versions

This project is experimental. Security fixes are made on the latest `main` branch;
older commits and forks have no separate support commitment.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting:
[Report a vulnerability](https://github.com/ROSITO/studio-avatar/security/advisories/new).
Include reproduction steps, affected commits, impact, and a minimal sanitized
example. Do not publish credentials, personal media, or exploit details in issues.
If the private form is unavailable, use the maintainer's available GitHub profile
contact channel to request a private reporting method without disclosing details.

Reports are handled on a best-effort volunteer basis; no response-time SLA is
promised. Please coordinate public disclosure after a fix is available.

## Deployment boundary

This is a trusted, single-user localhost application, not a hosted service.
It has no authentication, permits uploads and computational jobs, and invokes
external engines. Keep its loopback binding and do not expose it through public
ports or untrusted proxies. Protect local model files and engine installations.
Review external engine/model licenses and security updates independently.
