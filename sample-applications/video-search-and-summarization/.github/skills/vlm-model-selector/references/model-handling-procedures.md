<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Model Handling Procedures (conditional sub-procedures for `vlm-model-selector`)

These two procedures apply only when the situation arises during Step 5's model-card review — most candidates need neither. Follow them in full when they apply; do not compress or skip steps.

## Handling a gated candidate (access-request wall)

Some Hub models (e.g., several MiniCPM-V and Llama-derived VLM checkpoints) sit behind a gate: the repo page shows an access-request wall, and downloads/API calls return 401/403 until the user's own Hugging Face account has accepted the terms. The agent can read the public parts of the page (license summary, capability description) but **cannot accept the gate on the user's behalf** — only the user's own account can agree to it. A Hugging Face access token is a secret: never ask for its value in a chat question, and never type or relay one into a terminal login prompt yourself.

1. Tell the user the candidate is gated, summarize what the gate actually asks for from the model page (e.g., contact-info sharing, an academic-use affirmation, a commercial-registration step), and link to the model page so they can read the real terms themselves.
2. Ask a plain yes/no question — never one requesting a secret value — about whether they already have access to this model on their Hugging Face account and have an auth token available locally. Confirm *that* a token exists, never *what* it is.
3. If they haven't accepted the gate yet: give them the exact model URL and ask them to log in to huggingface.co with their own account and click "Agree and access repository" there. Do not attempt this for them.
4. If they don't have a token set up: tell them to create a **Read**-scope token at https://huggingface.co/settings/tokens, then either set it as the `HF_TOKEN` environment variable in their own shell/profile, or run `huggingface-cli login` themselves and type the token directly at that prompt. If you (the agent) run `huggingface-cli login` in a shared terminal and it pauses waiting for the token, stop and tell the user to type it directly into that terminal — do not send it for them.
5. Once the user confirms both steps are done, verify *presence only*, never the value — e.g., check that `HF_TOKEN`/`HUGGING_FACE_HUB_TOKEN` is set, or run `huggingface-cli whoami` to confirm authentication succeeded — before continuing the model-card review or attempting an export for that candidate.
6. If the user declines or can't get access, drop the candidate (same handling as a Bucket 3 license in `license-taxonomy.md`) and continue with the next-best candidate instead of blocking the whole recommendation on it.

## Handling a model that requires custom code (`--trust-remote-code`)

Some Hub checkpoints ship a custom `modeling_*.py`/`configuration_*.py` file and only load with `trust_remote_code=True` (`optimum-cli export openvino`'s `--trust-remote-code` flag). That flag executes arbitrary Python from the selected Hub repository locally, with the user's own permissions and whatever credentials are available in that environment — it is a code-execution decision, not a compute-fit or license decision. Passing a candidate's license and architecture-compatibility checks **never** establishes that its code is safe to run, so never enable this flag by default.

1. Default to running every export or feasibility probe **without** `--trust-remote-code`. Try it without the flag first.
2. If the export fails specifically because the architecture needs custom code (check the error output and the model card for a `trust_remote_code` mention), stop and do not add the flag yourself. Tell the user: name the exact repo, identify the exact revision you'd need to run (a commit SHA, not a floating `main`/branch pointer that can change later), and describe what the custom code file(s) do if that's visible from the repo.
3. Only add `--trust-remote-code` after the user explicitly approves running that specific pinned revision's code. Never enable it silently or because it's the only way to "make the export work" — if the user doesn't approve, drop the candidate (or keep it only as a Plausible/Unknown-tier option with compute-fit explicitly marked unverified) and continue with the next-best candidate instead of blocking the whole recommendation on it.
4. When the user does approve, pin the revision in the actual command (e.g. `--model <hf-model-id>@<commit-sha>`) rather than the bare repo id, so a later, unreviewed commit to the same repo can't silently change what code executes on a subsequent run.
