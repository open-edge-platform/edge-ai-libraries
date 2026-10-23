<!--
  Copyright (C) 2026 Intel Corporation
  SPDX-License-Identifier: Apache-2.0
-->

# Uninstall

## OpenShell profiles

```bash
./uninstall.sh --runtime openshell --yes
```

This removes both installer-owned sandboxes/providers and their chat/workspace
data, shared IR/OVMS and private backend network, model downloads, and installer
state. Back up needed data before consenting. The OpenShell local gateway
service, Debian CLI package and user state are also removed when this deployment
installed them (`openshell-owned` receipt). Pre-existing OpenShell installations
are preserved. Remaining unrelated sandboxes/providers/gateway registrations or
another account's running gateway block system-wide OpenShell removal.

Failures retain remaining ownership/transition state for retry instead of
reporting complete cleanup. Legacy installations without an OpenShell ownership
receipt are not automatically claimed. `--keep-agent-data` cannot retain a
deleted sandbox's home; back it up instead.

For deliberately scoped removal without removing shared inference/OpenShell:

```bash
./uninstall.sh --runtime openshell --sandbox-only --harness openclaw --yes
./uninstall.sh --runtime openshell --sandbox-only --harness hermes --yes
```

This mode retains `removed-profile.json` for audit. CI always uses this scoped
mode when testing against a shared prepared runner.

## Host installation

```bash
./uninstall.sh                  # prompts, deletes downloaded models by default
./uninstall.sh --yes --delete-models --harness openclaw
./uninstall.sh --yes --keep-models   # explicitly retain downloaded models
./uninstall.sh --yes --keep-agent-data --harness hermes   # keep ~/.hermes (sessions, memories, skills)
```

Removes the Inference Router container and, if this install started one, the
OpenVINO Model Server container, the private backend network, the
installed agent (its actual package — e.g. `npm
uninstall -g openclaw`, `uv tool uninstall deepagents-code`, or Hermes's own
data directory `~/.hermes` — not just its CLI shim), and the
`~/.agent-harness-install` state directory. Owned OpenShell sandboxes and an
installer-owned OpenShell runtime are removed too. Model deletion is the default;
`--delete-models` remains a compatibility alias. Pass `--keep-agent-data` to
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
