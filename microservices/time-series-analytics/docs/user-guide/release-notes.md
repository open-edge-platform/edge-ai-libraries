# Release Notes: Time Series Analytics

## Version 2026.1

**June, 2026**
This release introduces new deployment flexibility features, a UDF management API, security
fixes, and a modernized base image for Time Series Analytics.

**New**

- Added optional CPU core-pinning support via the `CORE_PINNING` environment variable, allowing the service to prefer specific core types (E-cores, P-cores, or low-power cores).
- Added a `/udfs/package` API endpoint to upload and extract UDF deployment packages as tar archives via HTTP, enabling UDF updates without manual file placement.

**Improved**

- Changed the base Docker image from the Kapacitor image to a Debian-based Python slim image with Kapacitor installed via `.deb`, reducing image size and improving flexibility.
- Updated Intel GPU drivers to support WCL (compute-runtime/IGC version `26.14.37833`).
- Updated Kapacitor version and Python library dependency versions.

---

## Version 2026.0

**March 27, 2026**
This release improves deployment consistency, reliability, and documentation usability for
Time Series Analytics.

**New**

- Standardized container image versioning across deployment methods.
- Updated Helm chart versioning format for clearer chart tracking.

**Improved**

- Fixed issues in API utility and Docker test workflows.
- Resolved unit test stability issues.
- Simplified documentation by removing outdated Model Registry references.
- Reorganized documentation structure and navigation for easier access.

For older release notes, check out:

- [Release notes 2025](./release-notes/release-notes-2025.md)

<!--hide_directive
```{toctree}
:maxdepth: 5
:hidden:

Release Notes 2025 <./release-notes/release-notes-2025.md>

```
hide_directive-->