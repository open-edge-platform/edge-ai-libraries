# Release Notes: Document Ingestion

## Version 2026.3.0

**November 2026**

**Improved**

- **MinIO Deployment**: replaced the MinIO image with a hardened Chainguard image pinned by digest, switched storage to a managed named Docker volume, and simplified the health check, removing the need for a host mount path.
- **Text Chunking**: enabled tiktoken-based token counting for document and URL ingestion, since the transformers library is not installable alongside the pinned huggingface_hub version.
- **Python Version and Dependencies**: raised the minimum supported Python version to 3.11 and refreshed dependencies to resolve known security vulnerabilities.
- **Documentation**: standardized admonitions, cleaned up git clone instructions, updated system requirements, and made container registry and tag settings configurable in the get started guide.

---

## Version 2026.1.0

**Release Date:** June 17, 2026

**New:**

- Updated pdf download curl command in documentation to download an actual PDF instead of a webpage.
- Added dependency health checks for the Document Ingestion service to improve service readiness and deployment stability.
