# Release Notes: Time Series Analytics

## Version 2026.2

**Release Date:** September 2026

This release introduces **updated Intel GPU driver support**, **removed Model Registry integration**, and **hardened path handling**, along with dependency upgrades and documentation improvements.

**Improved**

- **Intel GPU driver support**: Updated the Intel® GPU driver/compute-runtime stack to version `26.27.39122`, adding the corresponding install script logic for the new driver and IGC packages.
- **Deployment simplification**: Removed leftover Model Registry integration references (`MODEL_REGISTRY_URL` environment variable and related config) from Docker Compose and Helm deployment artifacts, and updated unit tests to match.
- **Security**: Bumped Kapacitor to `1.8.6`, `python-multipart` to `0.0.32`, and `setuptools` to `83.0.0` in `requirements.txt`.
- **Documentation**: Updated release notes structure, GitHub branch references, and Helm deployment links across the user guide.

**Fixed**

- **Path traversal hardening**: Added `sanitize_dir_name()` validation before deriving UDF working directories from configuration/environment input, addressing an SDLe-reported vulnerability in `classifier_startup.py`.

---

## Version 2026.1

**Release Date:** June 17, 2026

**New:**

- Support for optional CPU core-pinning enabled with the `CORE_PINNING`
  environment variable, which allows the service to prefer specific core types
  (E-cores, P-cores, or low-power cores).
- A `/udfs/package` API endpoint for uploading and extracting UDF deployment
  packages as tar archives via HTTP. The UDF updates do not require manual
  placement of files.

**Improved:**

- The base Kapacitor Docker image is replaced by a Debian-based Python slim
  image with Kapacitor installed via `.deb`, reducing image size and improving
  flexibility.
- Updated Intel® GPU drivers to support WCL (compute-runtime/IGC version `26.14.37833`).
- Updated the Kapacitor and Python library dependency versions.

## Version 2026.0

**Release Date:** March 27, 2026

This release improves deployment consistency, reliability, and documentation usability for
Time Series Analytics.

**New:**

- Standardized container image versioning across deployment methods.
- Updated Helm chart versioning format for clearer chart tracking.

**Improved:**

- Fixed issues in API utility and Docker test workflows.
- Resolved unit test stability issues.
- Simplified documentation by removing outdated Model Registry references.
- Reorganized documentation structure and navigation for easier access.

## Previous Releases

- [Release notes 2025](./release-notes/release-notes-2025.md)

<!--hide_directive
```{toctree}
:maxdepth: 5
:hidden:

Release Notes 2025 <./release-notes/release-notes-2025.md>

```
hide_directive-->