# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please report it responsibly.

**DO NOT** open a public GitHub issue for security vulnerabilities.

### How to Report

- **Intel PSIRT:** Report through the [Intel Product Security Center](https://www.intel.com/security),
  following Intel's [Vulnerability Handling Guidelines](https://www.intel.com/content/www/us/en/security-center/vulnerability-handling-guidelines.html)

### What to Include

- Description of the vulnerability
- Steps to reproduce
- Potential impact (affected component, API, or deployment)
- Suggested fix (if any)

### Response Timeline

- **Acknowledgment:** Within 3 business days
- **Initial Assessment:** Within 10 business days
- **Fix/Patch:** Dependent on severity (Critical: 7 days, High: 30 days, Medium: 90 days)

## Supported Versions

| Version  | Supported                |
|----------|--------------------------|
| latest   | ✅                       |
| < latest | ❌ (upgrade recommended) |

## Security Update Process

Security patches are released as part of regular releases. Critical vulnerabilities
may trigger an out-of-band patch release.

## Scope

This policy applies to the code in this repository. Third-party dependencies
are tracked via automated scanning (Dependabot/Trivy) and patched as updates
become available.

## Disclosure Policy

We follow [coordinated vulnerability disclosure](https://vuls.cert.org/confluence/display/Wiki/Coordinated+Vulnerability+Disclosure+Guidance).
We request a 90-day disclosure window from report to public disclosure.
