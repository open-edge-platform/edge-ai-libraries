# Release Notes: Document Summarization Sample Application

## Version 2026.3.0

**November 2026**

**Improved**

- **OpenVINO Model Server Upgrade**: upgraded OpenVINO Model Server to 2026.3 across Docker Compose, Helm charts, setup scripts, and model export instructions.
- **Default LLM Model**: changed the default LLM from microsoft/Phi-4 to Qwen/Qwen3-4B-Instruct-2507 in the Makefile, Helm values, and documentation.
- **Security**: updated package versions and the container image to address known security vulnerabilities.
- **Documentation**: standardized admonitions and updated references and branch checkout instructions in the user guide.

---

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
