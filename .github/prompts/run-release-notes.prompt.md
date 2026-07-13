
---
mode: agent
description: Generate formatted release notes for a product by comparing two branches or tags.
---

Generate release notes for **${input:productName:Product name (e.g. Time Series Analytics)}** by comparing `${input:baseBranch:Base branch or tag (e.g. main)}` → `${input:releaseBranch:Release branch or tag (e.g. release-2026.1.0)}`, version `${input:version:Version number (e.g. 2026.1.0)}`, released `${input:releaseDate:Release month and year (e.g. June 2026)}`, scoped to folder `${input:folderPath:Folder path in repo (e.g. microservices/time-series-analytics)}`.

Follow the instructions in [generate-release-notes skill](../skills/generate-release-notes/SKILL.md).
