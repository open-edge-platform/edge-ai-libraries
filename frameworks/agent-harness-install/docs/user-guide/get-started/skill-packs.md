<!--
  Copyright (C) 2026 Intel Corporation
  SPDX-License-Identifier: Apache-2.0
-->

# Hermes Skill Packs

A skill pack is a versioned bundle of Hermes skills supplied by an application
that uses AHI, for example a video search and summarization deployment. AHI
installs the pack, registers it with Hermes, and can optionally retire Hermes's
bundled default skills so that only the pack's skills and Hermes's essential
skills remain active.

Any number of packs from any number of applications can be installed side by
side. Skill packs apply to Hermes only, on both the host and OpenShell
runtimes. For other agents the commands print a notice and make no changes.

## Pack format

A pack is a directory, or a `.tar.gz`, `.tgz` or `.zip` archive of one:

```text
pack.json
skills/
  vss-search/
    SKILL.md
    references/ templates/ scripts/ assets/ examples/   (optional)
```

Example `pack.json`:

```json
{
  "schema": 1,
  "id": "vss",
  "version": "1.0.0",
  "description": "Video search and summarization skills",
  "defaults": "none"
}
```

| Field | Description |
| --- | --- |
| `schema` | Required. Always `1`. |
| `id` | Required. Lowercase letters, digits and `-`, up to 32 characters. Must match the id used to install the pack. |
| `version`, `description` | Free text shown by `skills list`. |
| `agents` | Optional. Defaults to `["hermes"]` and must include `hermes`. |
| `runtimes` | Optional subset of `host` and `openshell`. Defaults to both. |
| `defaults` | `keep` (default) leaves Hermes's bundled skills in place. `none` retires them; see [Default skills](#default-skills). |
| `strict_names` | When `true`, rejects skills whose names do not start with `<id>-`. |
| `skills` | Optional list of skill names. If present, it must match the directories under `skills/`. |

### Skill names

Skill directory names use lowercase letters, digits, `.`, `_` and `-`. Prefix
each name with the pack id (for example `vss-search`) to avoid collisions. A
missing prefix produces a warning, or an error when `strict_names` is set in
`pack.json` or `HARNESS_SKILLS_STRICT_NAMES=1`.

A name that is already used by another pack, or by a skill you wrote or
modified in `~/.hermes/skills`, is always rejected before any change is made.

## Install a pack

Install from a directory, an archive or an HTTPS URL. A URL source requires the
SHA-256 digest of the archive.

```bash
./install.sh skills add vss /opt/vss/skills
./install.sh skills add vss ./vss-skills.tar.gz --sha256 <hex>
./install.sh skills add vss https://example.com/vss-skills.tar.gz --sha256 <hex>
```

Packs can also be requested during an AHI install:

```bash
./install.sh --harness hermes --skills-pack 'vss=/opt/vss/skills'
./install.sh --harness hermes --skills-pack 'vss=https://example.com/vss-skills.tar.gz#sha256=<hex>'
```

### Drop-in files

An application that does not run AHI itself can provide a pack by placing a
file at `~/.agent-harness-install/skill-packs.d/<id>.json`:

```json
{"id": "vss", "source": {"type": "dir", "path": "/opt/vss/skills"}}
```

```json
{"id": "vss", "source": {"type": "url", "url": "https://example.com/vss-skills.tar.gz", "sha256": "<hex>"}}
```

`./install.sh` and `./install.sh skills sync` apply every drop-in file. AHI
never deletes drop-in files. The file and its directory must be owned by the
current user and must not be writable by group or others; otherwise the error
message shows the `chmod` or `chown` command to fix it.

### What the installer does

- Installs the pack read-only under `~/.agent-harness-install/skill-packs/<id>/`
  and adds it to `skills.external_dirs` in Hermes's `config.yaml`. Hermes's own
  skills directory is not changed, so `hermes update` cannot overwrite pack
  skills.
- Saves the original `config.yaml` once as `config.yaml.pre-skillpacks` before
  the first edit. The backup is never overwritten.
- Repeats safely: running the same command again changes nothing, and a changed
  pack with the same id replaces the installed copy.

### Archive limits

Archives are extracted safely. Absolute paths, `..`, symlinks, hard links,
devices and encrypted entries are rejected. Size limits can be adjusted with:

| Variable | Default |
| --- | --- |
| `HARNESS_SKILLS_MAX_BYTES` | 64 MiB (extracted size) |
| `HARNESS_SKILLS_MAX_FILES` | 5000 |
| `HARNESS_SKILLS_MAX_ARCHIVE_BYTES` | 128 MiB |

## Manage packs

```bash
./install.sh skills list               # packs, skills and default-skills state
./install.sh skills verify [id]        # check content and Hermes config; non-zero on problems
./install.sh skills sync               # apply drop-ins and re-wire config.yaml
./install.sh skills remove <id>
./install.sh skills restore-defaults   # restore retired default skills
```

`list` and `verify` do not take the deployment lock and can run during an
install.

## Default skills

Hermes ships bundled skills that can conflict with an application's own. A pack
with `"defaults": "none"` makes AHI keep only Hermes's essential skills:

- **New install:** AHI creates `~/.hermes/.no-bundled-skills` before installing
  Hermes, so only the essential skills are seeded.
- **Existing install:** AHI backs up `~/.hermes/skills` to
  `~/.agent-harness-install/hermes-skills-backup/<UTC time>/`, then moves the
  unmodified bundled skills out of it.
- **Kept:** essential skills, bundled skills you modified, skills you wrote and
  skills installed from a hub. `--skills-purge` (`HARNESS_SKILLS_PURGE=1`) also
  retires modified bundled skills, after backing them up.
- **Unknown essentials:** if AHI cannot determine Hermes's essential skills, it
  removes nothing.

Use `--skills-defaults auto|keep|none` (`HARNESS_HERMES_DEFAULT_SKILLS`) to
override the packs:

| Value | Behavior |
| --- | --- |
| `auto` | Follow the packs (default). |
| `keep` | Never retire anything. A pack that asks for `none` is installed and AHI reports that nothing was retired. |
| `none` | Always retire the bundled skills. |

`./install.sh skills restore-defaults` restores everything from the backup,
removes the marker file if AHI created it, and records `keep` so that packs do
not retire the skills again. To retire them again, run
`./install.sh skills sync --skills-defaults none`.

`./uninstall.sh` removes the backup together with the rest of the AHI state.

## OpenShell sandboxes

With `--runtime openshell`, the registered packs are built into the Hermes
sandbox image and listed in the sandbox's `config.yaml`. The host's Hermes is
not changed. Register packs with `./install.sh skills add ...` (without
`--runtime openshell`), or pass `--skills-pack` to the OpenShell install.

A sandbox keeps the skills it was built with. If the registered packs or the
default-skills policy no longer match, running the install again fails and asks
you to recreate the sandbox. Back up any data you need from the sandbox first.

```bash
./uninstall.sh --runtime openshell --harness hermes --sandbox-only --yes
./install.sh --runtime openshell --harness hermes ...
```

With `--runtime openshell`, `skills list` and `skills verify` also report
whether the sandbox matches the registry. The other `skills` commands are
rejected because the sandbox content is fixed at build time.

## Model requirements

Skills are loaded by the agent through tool calls. Use a model that supports
tool calling. Very small models, such as Qwen3-0.6B, can list the skills but may
fail to load them.
