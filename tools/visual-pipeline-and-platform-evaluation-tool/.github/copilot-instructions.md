<!--SPDX-License-Identifier: Apache-2.0-->

# Copilot Instructions

## Scope

These instructions apply to the entire repository.

## Project Context

- ViPPET is a hardware-evaluation tool for AI workloads.
- Backend: Python 3.12, FastAPI, Pydantic v2.
- Frontend: React 19, shadcn components, react-hook-form, zod, recharts, react-router.
- Runtime uses Docker Compose profiles: `cpu`, `gpu`, `npu`.

## Coding Rules

### Python

- Use type hints for new and modified code.
- Use `async`/`await` for FastAPI route handlers.
- Use Pydantic v2 APIs (for example `model_dump()`).
- Use `logging` (never `print()`).
- Keep changes small and focused.

### TypeScript

- Keep strict typing; avoid `any`.
- Follow feature-based structure under `ui/src/features/`.
- Use existing Redux Toolkit and Tailwind patterns.

## Repository Constraints

- Do not modify files under `shared/` as part of source changes.
- Do not commit `.env` files or model artifacts.
- Keep API schema and generated clients in sync when API changes.

## Validation Before Finishing

- Run relevant linters and tests for touched areas.
- For docs-only changes, ensure `markdownlint` passes.
- Do not include unrelated refactors in the same PR.
