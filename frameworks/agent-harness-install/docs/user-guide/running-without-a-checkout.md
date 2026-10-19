<!--
  Copyright (C) 2026 Intel Corporation
  SPDX-License-Identifier: Apache-2.0
-->

# Running Without a Checkout

`install.sh` is a thin bootstrap: if it finds `scripts/install.sh` next to it
(a normal checkout), it just runs that. If it's fetched standalone (e.g.
`curl -fsSL <url>/install.sh | bash`), it clones this installer's own repo at
a pinned ref into a temp dir first, then runs the payload from there:

```bash
export HARNESS_INSTALL_REPO=https://github.com/<you>/<your-fork>.git
export HARNESS_INSTALL_REF=v1.0.0   # required — a tag or commit of HARNESS_INSTALL_REPO
curl -fsSL https://raw.githubusercontent.com/<you>/<your-fork>/main/install.sh | bash
```

`HARNESS_INSTALL_REPO` has no default — this installer refuses to guess
which repo to clone. `HARNESS_INSTALL_REF` is also required in this mode —
this installer refuses to silently run whatever `main` currently contains.
If `HARNESS_INSTALL_REPO` is a monorepo where this installer lives under a
subdirectory (rather than at the repo root), set `HARNESS_INSTALL_SUBDIR` to
that path.

For this repo specifically (a monorepo, so `HARNESS_INSTALL_SUBDIR` is set),
with no local clone:

```bash
curl -fsSL https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/main/frameworks/agent-harness-install/install.sh \
  | HARNESS_INSTALL_REPO=https://github.com/open-edge-platform/edge-ai-libraries.git \
    HARNESS_INSTALL_SUBDIR=frameworks/agent-harness-install \
    HARNESS_INSTALL_REF=v1.0.0 bash
```

Installer flags/env after the piped script need `-s --` first, since stdin is
already consumed by the pipe:

```bash
curl -fsSL https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/main/frameworks/agent-harness-install/install.sh \
  | HARNESS_INSTALL_REPO=https://github.com/open-edge-platform/edge-ai-libraries.git \
    HARNESS_INSTALL_SUBDIR=frameworks/agent-harness-install \
    HARNESS_INSTALL_REF=v1.0.0 \
    bash -s -- --harness openclaw --non-interactive
```

If the repo is private, anonymous `curl`/`git fetch` will fail here (401/404)
— clone it with your own git credentials first and run `./install.sh` from
that checkout instead (the normal source-checkout path above).

`./install.sh` automatically runs the cloned repo's own `./startup.sh` first
(Docker/Node.js/Python) — this works in standalone mode too, since the
pinned ref is fetched in full to the temp dir before anything runs, so
`startup.sh` is right there alongside `scripts/install.sh`. The temp clone
is still removed as soon as `install.sh` exits, so there's nothing left to
run `./startup.sh` from directly afterward -- if you want to pre-provision
a host or re-run just the prerequisite step on its own, use a real
`git clone` (the normal source-checkout path above) instead.
