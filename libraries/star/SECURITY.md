# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in this project (STAR: Semantic Compression
Toolbox with Adaptive Rate — Image Pipeline), please report it responsibly.

**DO NOT** open a public GitHub issue for security vulnerabilities.

### How to Report

- **GitHub:** [Report a vulnerability](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/report-privately) (preferred)
- **Email:** psirt@intel.com (Intel Product Security Incident Response Team)

See Intel's [Security Center](https://www.intel.com/content/www/us/en/security-center/default.html)
for general vulnerability reporting guidance.

### What to Include

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

### Response Timeline

- **Acknowledgment:** Within 3 business days
- **Initial Assessment:** Within 10 business days
- **Fix/Patch:** Dependent on severity (Critical: 7 days, High: 30 days, Medium: 90 days)

## Supported Versions

| Version | Supported |
|---------|-----------|
| latest  | ✅        |
| < latest | ❌ (upgrade recommended) |

## Security Update Process

Security patches are released as part of regular releases. Critical vulnerabilities
may trigger an out-of-band patch release.

## Scope

This policy applies to the code in this repository, including the encoder/decoder
pipeline, Docker/Compose deployment assets, and finetuning/evaluation tooling. Third-party
dependencies (Python packages, container base images) are tracked via automated scanning
(Dependabot/Trivy/pip-audit) and patched as updates become available.

## Disclosure Policy

We follow [coordinated vulnerability disclosure](https://vuls.cert.org/confluence/display/Wiki/Coordinated+Vulnerability+Disclosure+Guidance).
We request a 90-day disclosure window from report to public disclosure.
