# Release Notes: Document Summarization Sample Application

## Version 2026.2.0

<!--date TBD-->

**Fixed:**

- Added NLTK_DATA environment variable and improved NLTK corpus download with quiet mode and fail-fast error handling during image builds
- Fixed security vulnerablity issues

**Known Issues:**

- EMF Deployment package is not supported.
- Summary time depends on the size and complexity (image, tables, cross references) of the document.

## Version 2026.1.0

**Release Date:** June 17, 2026

**Fixed:**

- Fixed the LlamaIndex import issue by replacing the deprecated BaseLlamaPack dependency with an updated import structure.

## Version 1.0.5

**Release Date:** 25 Mar 2026

**Fixed:**

- Fix security vulnerabilities by updating several package versions.

## Version 1.0.4

**Release Date:** 17 Feb 2026

**Improved:**

- Updated default `CHUNK_SIZE` to 4096 to support larger files and updated supporting documents

## Previous Releases

- [Release Notes 2025](./release-notes/release-notes-2025.md)

<!--hide_directive
:::{toctree}
:hidden:

Release Notes 2025 <release-notes/release-notes-2025.md>

:::
hide_directive-->
