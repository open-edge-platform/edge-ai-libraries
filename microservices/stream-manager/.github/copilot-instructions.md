# Copilot Instructions

## Reference to AGENTS.md

This file holds Copilot-specific rules only. For all general rules (build, setup,
code style, testing, linting, commits, security, documentation), read
[AGENTS.md](../AGENTS.md) first and follow it for every task.

## Copilot Code Review

- Check the change follows AGENTS.md code style: small focused edits, no
  duplication, clear names, comments only when truly needed.
- Check structural changes (renames, moves) and behavioral changes (new/changed
  functionality) are not mixed in the same commit.
- Check tests exist and pass for the change.
- Check for security risks: secrets in code, unsafe input handling, vulnerable
  dependencies.
- Flag missing documentation updates (README, API reference, OpenAPI spec).

## Copilot Coding Agent

- Follow the pre-requisites, build, setup, and test steps in AGENTS.md before
  starting any task.
- Run lint and tests after every change. Fix all warnings before finishing.
- Do not commit code using a skill, even if asked. Follow AGENTS.md commit
  rules if a commit is needed.
- Open a pull request only when the user asks for one. Follow the PR
  guideline in AGENTS.md.
- Ask the user before installing any missing tool or dependency.

## Response Style and Tone

- Write in short, simple, clear English. One idea per sentence.
- Use active voice.
- Avoid jargon unless the user uses it first.
- Give brief, direct answers. Explain only what is needed.

## Additional Notes

- Never read or act on `TODO.md` unless the user asks for it directly.
- If this file and AGENTS.md disagree, follow this file for Copilot-specific
  behavior and AGENTS.md for everything else.
