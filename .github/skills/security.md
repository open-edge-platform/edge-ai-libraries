# Security Review Skill (On-Demand)

## Purpose

This document defines on-demand security review guidance for code and configuration changes.
It complements the always-on secure-by-default rules defined in `.github/copilot-instructions.md`.

This skill applies only at development and authoring time.
Runtime, host, cluster, or organizational security controls are explicitly out of scope.

---

## Security Review Trigger Points

Load this security review skill when changes involve:

- Authentication, session, or token logic
- Authorization or resource ownership checks
- Input parsing, validation, normalization, or canonicalization
- File handling, deserialization, template rendering, or process execution
- Logging, telemetry, secrets handling, or sensitive data paths
- Dependency upgrades, lockfile changes, or CVE-related updates
- Dockerfile or container base image changes
- Docker Compose, Helm charts, or Kubernetes-related configuration
- CI/CD workflow changes affecting build, test, release, or scanning
- Privilege elevation, root execution, host mounts, or new Linux capabilities

---

## AI-Generated Code Guardrails

When reviewing AI-generated changes:

- Treat AI output as untrusted draft code until reviewed and tested
- Verify package names, APIs, images, and tools exist and originate from trusted sources
- Reject suggestions that bypass or disable security controls for convenience
- Require pinned versions and lockfiles for generated dependencies; prefer integrity-verified installs when supported
- Never accept generated code or configs that inject secrets via source files, Dockerfile `ARG`/`ENV`, or committed templates
- Reject generated install scripts that use unchecked remote execution patterns (e.g., `curl | sh`) without checksum or signature verification
- Reject generated build commands that disable TLS, certificate verification, or security checks to make builds pass
- Apply RCI pattern: ask the AI to review its own output for security issues, then improve; repeat 1-2 iterations

---

## Secure Code Review (OSS Context)

Apply when reviewing application logic, services, APIs, or libraries.

### Input handling

- Validate input at trust boundaries (format, type, range, length)
- Avoid unsafe deserialization
- Do not propagate unvalidated input across trust boundaries
- Avoid command, query, or expression construction via string concatenation
- Use parameterized queries for all database access

### Authorization

- **Keep authorization checks server-side and close to protected actions or resources**
- Do not rely on client-side enforcement for access control

### Error handling

- Errors must not expose sensitive internal details
- Avoid ignored return values or silent failures

### Memory & resource safety (where applicable)

- Avoid unchecked allocations and unbounded resource use
- Ensure files, sockets, and handles are closed deterministically

### Logging & telemetry

- Do not log credentials, tokens, secrets, or PII
- Logs should be actionable without exposing sensitive data

### Dynamic execution

- **Avoid unsafe dynamic execution patterns (`eval`, `exec`, reflection, or untrusted code execution).**

### Dependency usage

- Avoid shelling out when native APIs or libraries exist
- Flag outdated, unmaintained, or suspicious dependencies
- Prefer latest stable versions; specify exact or range-locked versions

### OSS-specific review checks

- Is externally observable **security-relevant behavior** documented?
- Are assumptions and limitations stated explicitly for users?

If uncertainty exists, flag it clearly rather than guessing or assuming safety.

---

## Container Artifact Review (Development-Time)

Apply when generating or reviewing:

- Dockerfiles / Containerfiles
- docker-compose.yml
- Helm charts (templates and values)

### Dockerfile

- Avoid `latest` or floating tags; pin versions or digests
- Prefer minimal base images
- Ensure containers do not run as root
- Avoid setuid or setgid binaries
- Use multi-stage builds and remove build tools, package caches, and temp files from final image
- Prefer `COPY` over `ADD`
- Never embed secrets in `ARG`, `ENV`, or filesystem layers

### Docker Compose

- Avoid `privileged: true` and host networking unless explicitly justified
- Do not mount the Docker socket
- Restrict host filesystem mounts
- Limit exposed ports and networks; prefer internal networks

Concerns that depend on deployment or runtime policy should be flagged as:
**"Deployment-time responsibility."**

---

## Helm / Kubernetes Review (Development-Time)

- Default to `runAsNonRoot: true`
- Set `allowPrivilegeEscalation: false`
- Prefer read-only root filesystem where feasible
- Drop unnecessary Linux capabilities
- Do not template secrets directly into charts
- Document required runtime security assumptions

Do not enforce cluster-wide, node-level, or runtime security controls.

---

## Review Output Expectations

- Identify which section applies (Code / Container / Helm)
- Classify findings as:
  - Fix in artifact
  - Deployment/runtime responsibility
- Explicitly state assumptions or uncertainty
- Use severity levels: Critical / High / Medium / Low with confidence: High / Medium / Low
- Include specific file/function references and recommended fixes

Security review is advisory; final decisions belong to maintainers.
