# Release Notes: Document Ingestion

## Version 2026.2.0

**Release Date:** September 9, 2026

**Fixes:**

- Replaced the MinIO image with the Chainguard MinIO image and migrated its host bind mount to a named Docker volume to avoid host filesystem permission issues.
- Enabled `tiktoken=true` for OpenAI embeddings to fix URL and document ingestion issues caused by the earlier transformer removal. The transformer could not be reintroduced because of dependency conflicts.

## Version 2026.1.0

**Release Date:** June 17, 2026

**New:**

- Updated pdf download curl command in documentation to download an actual PDF instead of a webpage.
- Added dependency health checks for the Document Ingestion service to improve service readiness and deployment stability.
