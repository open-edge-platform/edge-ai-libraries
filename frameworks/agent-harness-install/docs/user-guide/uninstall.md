<!--
  Copyright (C) 2026 Intel Corporation
  SPDX-License-Identifier: Apache-2.0
-->

# Uninstall

```bash
./uninstall.sh                  # prompts, keeps exported models
./uninstall.sh --yes --delete-models --harness openclaw
./uninstall.sh --yes --keep-agent-data --harness hermes   # keep ~/.hermes (sessions, memories, skills)
```

Removes the Inference Router container and, if this install started one, the
OpenVINO Model Server container (and, for a source build
via `HARNESS_IR_BUILD_FROM_SOURCE=1`, the locally built Inference Router image), the
installed agent (its actual package — e.g. `npm
uninstall -g openclaw`, `uv tool uninstall deepagents-code`, or Hermes's own
data directory `~/.hermes` — not just its CLI shim), and the
`~/.agent-harness-install` state directory. Pass `--keep-agent-data` to
preserve Hermes's or dcode's config/sessions/memories/skills instead of
deleting them. An agent data directory is only deleted if it is an absolute,
non-symlink path that is not `$HOME` or one of its parents (guarding a
mistyped `HERMES_HOME`/`DEEPAGENTS_HOME`); otherwise it is left in place with
a warning.

Left in place: Docker, Node.js/nvm, the Intel compute runtime, the Docker
daemon proxy drop-in (if one was written), the downloaded OVMS and Inference
Router images, the PATH
block added to your shell profile, and OpenClaw's own `~/.openclaw` config
(including the `ovms` provider it was pointed at) — remove those yourself if
you no longer need them.
