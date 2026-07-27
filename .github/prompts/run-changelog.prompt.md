
---
mode: agent
description: Generate or update CHANGELOG.md by comparing two branches, tags, or commits.
---

Generate a changelog entry for folder `${input:folderPath:Folder path or repo root (e.g. microservices/time-series-analytics)}`, comparing `${input:baseRef:Base branch or tag (e.g. release-2026.0.0)}` → `${input:targetRef:Target branch or tag (e.g. release-2026.1.0)}`, version label `${input:versionLabel:Version label (e.g. 2026.1.0) — leave blank to infer from branch name}`, release date `${input:releaseDate:Release month and year (e.g. June 2026) — leave blank to use commit date}`.

Follow the instructions in [generate-changelog skill](../skills/generate-changelog/SKILL.md).
