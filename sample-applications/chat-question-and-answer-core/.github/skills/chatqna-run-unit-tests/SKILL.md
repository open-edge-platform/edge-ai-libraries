---
name: chatqna-run-unit-tests
description: >
  Run ChatQnA Core unit tests for backend (pytest via uv) and frontend UI (vitest),
  including runtime selection (openvino or ollama), coverage options, and concise pass/fail evidence.
  Use this skill when the user says "run unit tests", "run backend tests", "run UI tests", "pytest", or "vitest".
license: Apache-2.0
metadata:
  version: "1.0.0"
  tags: "chatqna tests unit-tests pytest vitest backend frontend openvino ollama"
argument-hint: >
  Describe what to test and scope, for example "run backend openvino tests", "run UI tests with coverage", or "run all unit tests".
---

<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# ChatQnA Run Unit Tests

Run unit tests for Chat Question-and-Answer Core backend and frontend UI using
the repository-supported commands.

## Environment setup (run first)

This skill operates on real ChatQnA source files, so the ChatQnA application
must be present and commands must run from the app root. Do this before any
test workflow, whether or not source is already in your workspace.

Run the bundled bootstrap. It searches for an existing ChatQnA checkout by
walking up from the current directory and checking the enclosing git repo, then
reuses it without re-cloning. Only when no checkout is found does it do a
shallow, single-branch, sparse checkout of just
`sample-applications/chat-question-and-answer-core` from `main`.

It prints the resolved app root on stdout:

```bash
# SKILL_DIR is this skill directory. In-repo it is:
# .github/skills/chatqna-run-unit-tests
SKILL_DIR=".github/skills/chatqna-run-unit-tests"
APP_ROOT="$(bash "$SKILL_DIR/scripts/chatqna-bootstrap.sh")"
cd "$APP_ROOT"
```

Every command below assumes the working directory is this `APP_ROOT`.

To use a fork/branch or a specific clone path, override these before running
the bootstrap script:

- `CHATQNA_REPO_URL`
- `CHATQNA_REPO_BRANCH`
- `CHATQNA_CLONE_DIR`
- `CHATQNA_FORCE_CLONE` (set to `1` to force clone)

Codebase root: `sample-applications/chat-question-and-answer-core/`

## What This Skill Produces

- Executed unit tests for one or both scopes:
	- Backend (`pytest` via `uv run`)
	- Frontend UI (`vitest` via `npm run`)
- Optional coverage execution for backend and UI.
- A concise test report containing:
	- scope executed (backend/ui/both)
	- runtime used for backend (`openvino` or `ollama`)
	- pass/fail status and failing test identifiers
	- exact command(s) run as evidence

## When to Use

- After user-visible application code changes in backend or UI, run unit tests by
	default to validate regressions.
- Treat unit-test execution as the default post-change validation step unless the
	user explicitly says not to run tests.
- Skip unit-test execution only when the user clearly opts out (for example:
	"do not run tests", "skip unit tests", "no tests needed").
- "Run unit tests"
- "Run backend tests"
- "Run UI tests"
- "Run pytest"
- "Run vitest"
- "Run test coverage"

## Inputs To Confirm

Before running commands, confirm or infer:

1. Scope: `backend`, `ui`, or `both` (default: `both`)
2. Backend runtime: `openvino` or `ollama` (default: `openvino`)
3. Coverage mode: `on` or `off` (default: `off`)
4. Optional target narrowing (single file or test pattern)

If the user asks for "all unit tests", run backend + UI.

## Decision Logic

- If scope is `backend`:
	- run backend test workflow only
- If scope is `ui`:
	- run UI test workflow only
- If scope is `both`:
	- run backend workflow first, then UI workflow
- If backend runtime is not provided:
	- default to `openvino`
- If coverage is requested:
	- backend: add `--cov=app --cov-report=term-missing`
	- UI: use `npm run coverage`

## Workflow

Run from `sample-applications/chat-question-and-answer-core`.

### 1. Preflight

```bash
python3 --version
uv --version
node --version
npm --version
```

### 2. Backend Unit Tests

Install/sync dependencies if needed:

```bash
uv sync --all-groups
```

Run backend tests by runtime:

```bash
# OpenVINO backend tests (default)
uv run pytest --model-runtime=openvino

# Ollama backend tests
uv run pytest --model-runtime=ollama
```

Backend coverage mode:

```bash
# OpenVINO coverage
uv run pytest --model-runtime=openvino --cov=app --cov-report=term-missing

# Ollama coverage
uv run pytest --model-runtime=ollama --cov=app --cov-report=term-missing
```

### 3. Frontend UI Unit Tests

Switch to UI directory and install deps if needed:

```bash
cd ui
npm install
```

Run UI tests:

```bash
npm run test
```

UI coverage mode:

```bash
npm run coverage
```

Optional interactive runner (only when explicitly requested):

```bash
npm run test:ui
```

### 4. Optional Targeted Test Runs

Backend single file:

```bash
uv run pytest tests/test_server.py --model-runtime=openvino
```

UI targeted pattern example:

```bash
cd ui
npm run test -- Conversation
```

## Failure Handling

- `uv` not installed:
	- install `uv` and re-run sync/tests
- Backend dependency or import failures:
	- run `uv sync --all-groups` and retry
- `npm` or node_modules issues:
	- run `npm install` in `ui/` and retry
- Runtime mismatch for backend tests:
	- re-run with explicit `--model-runtime=openvino|ollama`
- Failing tests:
	- report failing test names and first actionable traceback lines

## Completion Criteria

1. Requested test scope (backend/ui/both) is executed.
2. For backend, runtime selection is explicit (`openvino` or `ollama`).
3. If coverage requested, coverage command(s) are run.
4. Response includes exact commands and pass/fail evidence.
5. If failures occur, response includes failing tests and next actionable step.
