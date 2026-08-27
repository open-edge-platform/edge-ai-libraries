# Release Notes: Vector Retriever - Milvus

<!--## Version 2026.2.0-->

<!--date TBD-->

## Version 2026.1.0

**Release Date:** June 17, 2026

**Fixed:**

- Docker base images for both the visual data preparation for retrieval and vector retriever Milvus services updated from the pinned `python:3.12.12-slim` to the rolling `python:3.12-slim`; the build now runs a full apt-get upgrade to apply all available OS-level security patches, and apt-get clean is performed to reduce image size.

- `astapi` upgraded from `0.121.1` to `0.121.3` and `pydantic` from `2.9.1` to `2.10.6` to resolve dependency scan findings.

## Previous Releases

- [Release notes 2025](./release-notes/release-notes-2025.md)

<!--hide_directive
```{toctree}
:hidden:

Release Notes 2025 <./release-notes/release-notes-2025.md>

```
hide_directive-->
