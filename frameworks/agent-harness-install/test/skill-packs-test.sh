#!/usr/bin/env bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# Unit tests for Hermes skill packs (scripts/lib/skill-packs.{sh,py}). No Docker, Hermes or network is used.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
. "$SCRIPT_DIR/scripts/install.sh"
. "$SCRIPT_DIR/test/openshell-test-lib.sh"
TEST_ROOT="$(mktemp -d)"
trap 'rm -f -- "$TEST_LOG"; chmod -R u+w -- "$TEST_ROOT" 2>/dev/null || true; rm -rf -- "$TEST_ROOT"; skills_openshell_clean_context' EXIT

# SKILL_TEST_FILTER=<substring> runs only the matching cases.
eval "orig_$(declare -f run_case)"
run_case() {
  [[ -z "${SKILL_TEST_FILTER:-}" || "$1" == *"$SKILL_TEST_FILTER"* ]] || return 0
  if [[ -n "${SKILL_TEST_TRACE:-}" ]]; then
    (set -euxo pipefail; "${@:2}") 2>&1 | tail -n 80 || true
    return 0
  fi
  orig_run_case "$@"
}

printf 'TAP version 13\n'
if ! python3 -c 'import yaml' 2>/dev/null; then
  printf '1..0 # SKIP python3 with PyYAML is required\n'
  exit 0
fi

# Path form Python understands (Git Bash on Windows maps /tmp to a drive path).
native_path() {
  (cd "$1" && { pwd -W 2>/dev/null || pwd; })
}

fixture() {
  export HOME TMPDIR HERMES_HOME
  HOME="$(mktemp -d "$TEST_ROOT/home.XXXXXX")"
  TMPDIR="$HOME/tmp"
  mkdir -p "$TMPDIR"
  HARNESS_STATE_DIRNAME=.harness-test
  HERMES_HOME="$HOME/.hermes"
  unset HERMES_CONFIG HARNESS_SKILLS_STRICT_NAMES HARNESS_SKILLS_PURGE
  HARNESS_HERMES_DEFAULT_SKILLS=auto
  export HARNESS_HERMES_ESSENTIAL_SKILLS="essential-one"
  HARNESS_RUNTIME=host
  HARNESS_AGENT=hermes
  SKILL_PACK_SPECS=()
  ACTIONS="$HOME/actions"
  : >"$ACTIONS"
  docker() { printf 'unexpected docker: %s\n' "$*" >&2; return 98; }
  sudo() { printf 'unexpected sudo: %s\n' "$*" >&2; return 98; }
  openshell() { printf 'unexpected openshell: %s\n' "$*" >&2; return 98; }
  mkdir -p "$HERMES_HOME"
  printf 'model:\n  default: fixture-model\nskills:\n  external_dirs:\n    - /opt/other-skills\n' >"$HERMES_HOME/config.yaml"
}

# make_pack <dir> <id> <defaults> <skill>...
make_pack() {
  local dir="$1" id="$2" defaults="$3" skill
  shift 3
  mkdir -p "$dir/skills"
  printf '{"schema":1,"id":"%s","version":"1.2.3","description":"fixture pack","defaults":"%s"}\n' "$id" "$defaults" >"$dir/pack.json"
  for skill in "$@"; do
    mkdir -p "$dir/skills/$skill"
    printf -- '---\nname: %s\ndescription: fixture\n---\n# %s\n' "$skill" "$skill" >"$dir/skills/$skill/SKILL.md"
  done
}

# Hermes's bundled skills with a .bundled_manifest in Hermes's own md5 format.
seed_hermes_skills() {
  local skills="$HERMES_HOME/skills" name
  for name in alpha beta essential-one modified; do
    mkdir -p "$skills/cat/$name"
    printf -- '---\nname: %s\ndescription: bundled\n---\n# %s\n' "$name" "$name" >"$skills/cat/$name/SKILL.md"
  done
  python3 - "$(native_path "$skills")" <<'PY'
import hashlib, os, sys
root = sys.argv[1]
lines = []
for name in sorted(os.listdir(os.path.join(root, "cat"))):
    base = os.path.join(root, "cat", name)
    digest = hashlib.md5()
    for rel in sorted(os.listdir(base)):
        digest.update(rel.encode())
        digest.update(open(os.path.join(base, rel), "rb").read())
    lines.append(f"{name}:{digest.hexdigest()}")
open(os.path.join(root, ".bundled_manifest"), "w").write("\n".join(lines) + "\n")
PY
  printf 'local edit\n' >>"$skills/cat/modified/SKILL.md"
  mkdir -p "$skills/mine/own-skill"
  printf -- '---\nname: own-skill\n---\n# mine\n' >"$skills/mine/own-skill/SKILL.md"
}

config_lists() {
  grep -Eq "$1" "$HERMES_HOME/config.yaml"
}

two_packs_coexist() {
  fixture
  make_pack "$HOME/src-a" aa keep aa-one aa-two
  make_pack "$HOME/src-b" bb keep bb-one
  skills_cmd_add aa "$(native_path "$HOME/src-a")"
  skills_cmd_add bb "$(native_path "$HOME/src-b")"
  config_lists 'skill-packs.aa.skills'
  config_lists 'skill-packs.bb.skills'
  config_lists '/opt/other-skills'
  grep -Fq 'default: fixture-model' "$HERMES_HOME/config.yaml"
  skills_cmd_list >"$HOME/list.out" 2>&1
  grep -Fq aa "$HOME/list.out" && grep -Fq bb "$HOME/list.out"
  skills_cmd_verify
  skills_cmd_remove aa
  [[ ! -e "$(skills_root)/aa" && -d "$(skills_root)/bb/skills/bb-one" ]]
  ! config_lists 'skill-packs.aa.skills'
  config_lists 'skill-packs.bb.skills'
  config_lists '/opt/other-skills'
  skills_cmd_verify
  # Reinstalling the same directory is idempotent: one external_dirs entry per pack.
  skills_cmd_add bb "$(native_path "$HOME/src-b")"
  skills_sync_config
  [[ "$(grep -Ec 'skill-packs.bb.skills' "$HERMES_HOME/config.yaml")" == 1 ]]
}

installed_pack_is_read_only() {
  fixture
  make_pack "$HOME/src" ro keep ro-one
  skills_cmd_add ro "$(native_path "$HOME/src")"
  local file="$(skills_root)/ro/skills/ro-one/SKILL.md"
  [[ -f "$file" ]]
  [[ "$(stat -c %a "$file")" == 644 ]] && return 0
  [[ "$(stat -c %a "$file")" == 444 ]]
}

reinstall_repairs_a_modified_pack() {
  fixture
  make_pack "$HOME/src" rp keep rp-one
  skills_cmd_add rp "$(native_path "$HOME/src")"
  local file="$(skills_root)/rp/skills/rp-one/SKILL.md"
  chmod u+w "$file"
  printf 'tamper\n' >>"$file"
  expect_failure 'verification failed' skills_cmd_verify
  skills_cmd_add rp "$(native_path "$HOME/src")" >"$HOME/repair.out" 2>&1
  grep -Fq 'reinstalling' "$HOME/repair.out"
  skills_cmd_verify
  ! grep -Fq tamper "$file"
}

cross_pack_and_local_collisions() {
  fixture
  make_pack "$HOME/src-a" aa keep shared-skill
  make_pack "$HOME/src-b" bb keep shared-skill
  skills_cmd_add aa "$(native_path "$HOME/src-a")"
  expect_failure 'conflicting skill names' skills_cmd_add bb "$(native_path "$HOME/src-b")"
  [[ ! -e "$(skills_root)/bb" ]]
  make_pack "$HOME/src-c" cc keep user-skill
  mkdir -p "$HERMES_HOME/skills/mine/user-skill"
  printf -- '---\nname: user-skill\n---\nx\n' >"$HERMES_HOME/skills/mine/user-skill/SKILL.md"
  expect_failure 'already exists locally' skills_cmd_add cc "$(native_path "$HOME/src-c")"
  [[ ! -e "$(skills_root)/cc" ]]
}

prefix_warns_and_strict_fails() {
  fixture
  make_pack "$HOME/src" acme keep other-name
  skills_cmd_add acme "$(native_path "$HOME/src")" >"$HOME/out" 2>&1
  grep -Fq "does not start with 'acme-'" "$HOME/out"
  skills_cmd_remove acme
  HARNESS_SKILLS_STRICT_NAMES=1 expect_failure "does not start with 'acme-'" skills_cmd_add acme "$(native_path "$HOME/src")"
  [[ ! -e "$(skills_root)/acme" ]]
}

pack_validation_rejects_bad_input() {
  fixture
  make_pack "$HOME/src" vss keep vss-one
  expect_failure 'Invalid skill pack id' skills_cmd_add 'Bad_ID' "$(native_path "$HOME/src")"
  expect_failure 'id mismatch' skills_cmd_add other "$(native_path "$HOME/src")"
  printf '{"schema":1,"id":"vss","version":"1","description":"x","agents":["openclaw"]}\n' >"$HOME/src/pack.json"
  expect_failure 'does not support Hermes' skills_cmd_add vss "$(native_path "$HOME/src")"
  printf '{"schema":1,"id":"vss","version":"1","description":"x"}\n' >"$HOME/src/pack.json"
  mkdir -p "$HOME/src/skills/vss-one/bin"
  expect_failure 'not an allowed subdirectory' skills_cmd_add vss "$(native_path "$HOME/src")"
}

remote_sources_need_https_and_digest() {
  fixture
  expect_failure 'SHA-256 digest is required' skills_cmd_add vss https://example.invalid/vss.tar.gz
  expect_failure 'must use https' skills_cmd_add vss http://example.invalid/vss.tar.gz
  expect_failure 'must end in' skills_fetch_archive https://example.invalid/vss.bin "$(printf '0%.0s' {1..64})"
  expect_failure 'SHA-256 digest is required' skills_classify_source 'https://example.invalid/vss.tar.gz'
}

archive_digest_is_enforced() {
  fixture
  make_pack "$HOME/src" vss keep vss-one
  tar -czf "$HOME/vss.tar.gz" -C "$HOME/src" .
  local good bad
  good="$(sha256_of "$HOME/vss.tar.gz")"
  bad="$(printf '0%.0s' {1..64})"
  expect_failure 'sha256 mismatch' skills_cmd_add vss "$HOME/vss.tar.gz" --sha256 "$bad"
  [[ ! -e "$(skills_root)/vss" ]]
  skills_cmd_add vss "$HOME/vss.tar.gz" --sha256 "$good"
  [[ -d "$(skills_root)/vss/skills/vss-one" ]]
}

hostile_archives_are_rejected() {
  fixture
  python3 - "$(native_path "$HOME")" <<'PY'
import io, os, sys, tarfile, zipfile
home = sys.argv[1]
pack = b'{"schema":1,"id":"evil","version":"1","description":"x"}'
skill = b"---\nname: evil-one\n---\nx\n"

def base(tar):
    for name, data in (("pack.json", pack), ("skills/evil-one/SKILL.md", skill)):
        info = tarfile.TarInfo(name)
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))

def build(name, extra):
    with tarfile.open(os.path.join(home, name), "w:gz") as tar:
        base(tar)
        extra(tar)

def traversal(tar):
    info = tarfile.TarInfo("../escape.txt")
    info.size = 1
    tar.addfile(info, io.BytesIO(b"x"))

def symlink(tar):
    info = tarfile.TarInfo("skills/evil-one/link")
    info.type = tarfile.SYMTYPE
    info.linkname = "/etc/passwd"
    tar.addfile(info)

def hardlink(tar):
    info = tarfile.TarInfo("skills/evil-one/hard")
    info.type = tarfile.LNKTYPE
    info.linkname = "pack.json"
    tar.addfile(info)

def absolute(tar):
    info = tarfile.TarInfo("/tmp/abs.txt")
    info.size = 1
    tar.addfile(info, io.BytesIO(b"x"))

build("traversal.tar.gz", traversal)
build("symlink.tar.gz", symlink)
build("hardlink.tar.gz", hardlink)
build("absolute.tar.gz", absolute)
with zipfile.ZipFile(os.path.join(home, "zip-slip.zip"), "w") as z:
    z.writestr("pack.json", pack)
    z.writestr("skills/evil-one/SKILL.md", skill)
    z.writestr("../escape.txt", "x")
PY
  local name
  for name in traversal.tar.gz symlink.tar.gz hardlink.tar.gz absolute.tar.gz zip-slip.zip; do
    expect_failure 'did not pass validation' skills_cmd_add evil "$HOME/$name"
    [[ ! -e "$(skills_root)/evil" ]]
  done
  [[ ! -e "$HOME/escape.txt" && ! -e "$HOME/.harness-test/escape.txt" ]]
}

archive_size_limits_apply() {
  fixture
  make_pack "$HOME/src" big keep big-one
  head -c 4096 /dev/zero >"$HOME/src/skills/big-one/data.bin"
  HARNESS_SKILLS_MAX_FILE_BYTES=1024 expect_failure 'did not pass validation' skills_cmd_add big "$(native_path "$HOME/src")"
  HARNESS_SKILLS_MAX_FILES=1 expect_failure 'did not pass validation' skills_cmd_add big "$(native_path "$HOME/src")"
}

defaults_policy_resolution() {
  fixture
  make_pack "$HOME/src" nn none nn-one
  [[ "$(skills_effective_policy)" == keep ]]
  skills_cmd_add nn "$(native_path "$HOME/src")" >/dev/null 2>&1
  [[ "$(skills_effective_policy)" == none ]]
  HARNESS_HERMES_DEFAULT_SKILLS=keep
  [[ "$(skills_effective_policy)" == keep ]]
}

marker_precedes_hermes_install() {
  fixture
  rm -rf "$HERMES_HOME"
  make_pack "$HOME/src" nn none nn-one
  SKILL_PACK_SPECS=("nn=$(native_path "$HOME/src")")
  install_selected_agent() {
    [[ -f "$HERMES_HOME/.no-bundled-skills" ]] && printf 'marker-before-install\n' >>"$ACTIONS"
    seed_hermes_skills
    printf 'model:\n  default: fixture-model\n' >"$HERMES_HOME/config.yaml"
  }
  skills_pre_agent_install
  # Packs are only staged before the agent install; nothing is committed yet.
  [[ ! -e "$(skills_root)/nn" ]]
  install_selected_agent
  skills_post_agent_install
  grep -Fxq marker-before-install "$ACTIONS"
  [[ -d "$(skills_root)/nn/skills/nn-one" ]]
  config_lists 'skill-packs.nn.skills'
  # Pristine bundled skills are retired; essential, modified and user skills stay.
  [[ ! -e "$HERMES_HOME/skills/cat/alpha" && ! -e "$HERMES_HOME/skills/cat/beta" ]]
  [[ -d "$HERMES_HOME/skills/cat/essential-one" && -d "$HERMES_HOME/skills/cat/modified" ]]
  [[ -d "$HERMES_HOME/skills/mine/own-skill" ]]
  [[ -n "$(find "$(harness_state_root)/hermes-skills-backup" -name SKILL.md -path '*alpha*' -print -quit)" ]]
  skills_cmd_verify
}

bad_pack_aborts_before_agent_install() {
  fixture
  make_pack "$HOME/src" nn keep nn-one
  rm -f "$HOME/src/skills/nn-one/SKILL.md"
  SKILL_PACK_SPECS=("nn=$(native_path "$HOME/src")")
  expect_failure 'did not pass validation' skills_pre_agent_install
  [[ ! -e "$HERMES_HOME/.no-bundled-skills" ]]
}

retire_and_restore_defaults() {
  fixture
  seed_hermes_skills
  make_pack "$HOME/src" nn none nn-one
  skills_cmd_add nn "$(native_path "$HOME/src")" >/dev/null 2>&1
  [[ -f "$HERMES_HOME/.no-bundled-skills" ]]
  [[ ! -e "$HERMES_HOME/skills/cat/alpha" ]]
  [[ -d "$HERMES_HOME/skills/cat/modified" && -d "$HERMES_HOME/skills/cat/essential-one" ]]
  # Retiring again is a no-op.
  skills_cmd_sync >/dev/null 2>&1
  [[ "$(find "$(harness_state_root)/hermes-skills-backup" -mindepth 1 -maxdepth 1 | wc -l)" == 1 ]]
  skills_cmd_restore_defaults >/dev/null 2>&1
  [[ -f "$HERMES_HOME/skills/cat/alpha/SKILL.md" && -f "$HERMES_HOME/skills/cat/beta/SKILL.md" ]]
  [[ ! -e "$HERMES_HOME/.no-bundled-skills" ]]
  # restore-defaults is remembered: the packs do not retire them again.
  skills_cmd_sync >/dev/null 2>&1
  [[ -d "$HERMES_HOME/skills/cat/alpha" ]]
  # An explicit --skills-defaults none overrides that.
  HARNESS_HERMES_DEFAULT_SKILLS=none skills_cmd_sync >/dev/null 2>&1
  [[ ! -e "$HERMES_HOME/skills/cat/alpha" ]]
}

retirement_requires_known_essentials() {
  fixture
  seed_hermes_skills
  unset HARNESS_HERMES_ESSENTIAL_SKILLS
  make_pack "$HOME/src" nn none nn-one
  expect_failure 'essential skills' skills_cmd_add nn "$(native_path "$HOME/src")"
  [[ -d "$HERMES_HOME/skills/cat/alpha" && -d "$HERMES_HOME/skills/cat/essential-one" ]]
}

purge_retires_modified_skills() {
  fixture
  seed_hermes_skills
  make_pack "$HOME/src" nn none nn-one
  HARNESS_SKILLS_PURGE=1 skills_cmd_add nn "$(native_path "$HOME/src")" >/dev/null 2>&1
  [[ ! -e "$HERMES_HOME/skills/cat/modified" && -d "$HERMES_HOME/skills/cat/essential-one" ]]
  [[ -d "$HERMES_HOME/skills/mine/own-skill" ]]
}

dropin_packs_are_applied() {
  fixture
  make_pack "$HOME/src" dp keep dp-one
  local dir="$(harness_state_root)/skill-packs.d"
  mkdir -p "$dir"
  chmod 700 "$(harness_state_root)" "$dir"
  printf '{"id":"dp","source":{"type":"dir","path":"%s"}}\n' "$(native_path "$HOME/src")" >"$dir/dp.json"
  chmod 600 "$dir/dp.json"
  skills_cmd_sync >/dev/null 2>&1
  [[ -d "$(skills_root)/dp/skills/dp-one" ]]
  config_lists 'skill-packs.dp.skills'
  # A URL drop-in without a digest is rejected.
  printf '{"id":"up","source":{"type":"url","url":"https://example.invalid/up.tar.gz"}}\n' >"$dir/up.json"
  expect_failure 'drop-in' skills_cmd_sync
}

dropin_permissions_are_checked() {
  fixture
  make_pack "$HOME/src" dp keep dp-one
  local dir="$(harness_state_root)/skill-packs.d"
  mkdir -p "$dir"
  chmod 700 "$(harness_state_root)" "$dir"
  printf '{"id":"dp","source":{"type":"dir","path":"%s"}}\n' "$(native_path "$HOME/src")" >"$dir/dp.json"
  chmod 666 "$dir/dp.json"
  # Filesystems that ignore chmod (e.g. NTFS under Git Bash) cannot exercise this.
  [[ "$(stat -c %a "$dir/dp.json")" == 666 ]] || return 0
  expect_failure 'writable' skills_cmd_sync
  expect_failure "chmod go-w" skills_cmd_sync
  [[ ! -e "$(skills_root)/dp" ]]
}

local_clash_fails_before_retirement() {
  fixture
  seed_hermes_skills
  make_pack "$HOME/src" nn none own-skill
  expect_failure 'already exists locally' skills_cmd_add nn "$(native_path "$HOME/src")"
  [[ -d "$HERMES_HOME/skills/cat/alpha" && ! -e "$HERMES_HOME/.no-bundled-skills" ]]
  [[ ! -e "$(harness_state_root)/hermes-skills-backup" && ! -e "$(skills_root)/nn" ]]
  # A pack skill named like a bundled skill that is about to be retired is fine.
  make_pack "$HOME/src2" mm none alpha
  skills_cmd_add mm "$(native_path "$HOME/src2")" >/dev/null 2>&1
  [[ ! -e "$HERMES_HOME/skills/cat/alpha" && -d "$(skills_root)/mm/skills/alpha" ]]
  # A modified bundled skill is kept, so a pack skill with its name clashes.
  make_pack "$HOME/src3" pp none modified
  expect_failure 'already exists locally' skills_cmd_add pp "$(native_path "$HOME/src3")"
}

config_backup_is_written_once() {
  fixture
  local backup="$HERMES_HOME/config.yaml.pre-skillpacks"
  printf '# keep me\nmodel:\n  default: fixture-model\n' >"$HERMES_HOME/config.yaml"
  make_pack "$HOME/src-a" aa keep aa-one
  make_pack "$HOME/src-b" bb keep bb-one
  skills_cmd_add aa "$(native_path "$HOME/src-a")" >/dev/null 2>&1
  grep -Fq '# keep me' "$backup"
  ! grep -Fq '# keep me' "$HERMES_HOME/config.yaml"
  skills_cmd_add bb "$(native_path "$HOME/src-b")" >/dev/null 2>&1
  ! grep -Fq 'skill-packs' "$backup"
}

retirement_explains_silent_cases() {
  fixture
  make_pack "$HOME/src" nn none nn-one
  skills_cmd_add nn "$(native_path "$HOME/src")" >"$HOME/out" 2>&1
  grep -Fq 'no .bundled_manifest' "$HOME/out"
}

restore_defaults_choice_is_explained() {
  fixture
  make_pack "$HOME/src" nn none nn-one
  seed_hermes_skills
  skills_cmd_add nn "$(native_path "$HOME/src")" >/dev/null 2>&1
  skills_cmd_restore_defaults >/dev/null 2>&1
  # After restore-defaults a later none pack is not applied, and the user is told why.
  make_pack "$HOME/src2" pp none pp-one
  skills_cmd_add pp "$(native_path "$HOME/src2")" >"$HOME/out2" 2>&1
  grep -Fq 'restore-defaults' "$HOME/out2"
  [[ -d "$HERMES_HOME/skills/cat/alpha" ]]
}

non_hermes_agent_is_skipped() {
  fixture
  local out
  out="$(HARNESS_AGENT=openclaw run_skills_command list 2>&1)"
  grep -Fq 'Hermes only' <<<"$out"
  [[ ! -e "$(skills_root)" ]]
  HARNESS_AGENT=openclaw
  SKILL_PACK_SPECS=("x=$HOME")
  out="$(skills_pre_agent_install 2>&1)"
  grep -Fq 'Hermes only' <<<"$out"
  [[ ! -e "$(skills_root)" ]]
}

no_packs_means_no_changes() {
  fixture
  seed_hermes_skills
  local before
  before="$(find "$HERMES_HOME" -type f | sort | sha256sum)"
  skills_pre_agent_install
  skills_post_agent_install
  [[ "$(find "$HERMES_HOME" -type f | sort | sha256sum)" == "$before" ]]
  [[ ! -e "$HERMES_HOME/.no-bundled-skills" ]]
}

openshell_rejects_mutating_verbs() {
  fixture
  HARNESS_RUNTIME=openshell
  local verb
  for verb in add remove sync restore-defaults; do
    expect_failure 'baked into its image' run_skills_command "$verb" x y
  done
}

openshell_context_and_hash_guard() {
  fixture
  make_pack "$HOME/src" nn none nn-one
  skills_cmd_add nn "$(native_path "$HOME/src")" >/dev/null 2>&1
  HARNESS_RUNTIME=openshell
  skills_openshell_prepare
  [[ -n "$SKILLS_OPENSHELL_HASH" && "$SKILLS_OPENSHELL_DEFAULTS" == none ]]
  skills_openshell_stage_context hermes
  local ctx
  ctx="$(skills_openshell_context_dir)"
  grep -Fq '"nn"' "$ctx/manifest.json"
  grep -Fq '"defaults": "none"' "$ctx/manifest.json" || grep -Fq '"defaults":"none"' "$ctx/manifest.json"
  [[ -f "$ctx/nn/skills/nn-one/SKILL.md" ]]
  skills_openshell_clean_context
  [[ ! -e "$ctx" ]]
  skills_openshell_stage_context openclaw
  grep -Fq '"packs":[]' "$ctx/manifest.json"
  skills_openshell_clean_context
  # The recorded pack-set hash decides whether an existing sandbox is current.
  local profile
  profile="$(openshell_profile_dir)"
  mkdir -p "$profile"
  printf '{"owner":"x","name":"ahi-x","gateway":"g","agent":"hermes","model":"m"}\n' >"$profile/profile.json"
  OPENSHELL_NAME=ahi-x
  expect_failure 'changed since sandbox' skills_openshell_assert_unchanged "$SKILLS_OPENSHELL_HASH"
  skills_openshell_record_hash "$SKILLS_OPENSHELL_HASH"
  skills_openshell_assert_unchanged "$SKILLS_OPENSHELL_HASH"
  expect_failure 'changed since sandbox' skills_openshell_assert_unchanged ""
  [[ "$(skills_openshell_recorded_hash)" == "$SKILLS_OPENSHELL_HASH" ]]
  # A sandbox built before skill packs existed matches an empty keep set.
  printf '{"owner":"x","name":"ahi-x","gateway":"g","agent":"hermes","model":"m"}\n' >"$profile/profile.json"
  skills_openshell_assert_unchanged ""
}

openshell_packs_do_not_touch_host_hermes() {
  fixture
  seed_hermes_skills
  make_pack "$HOME/src" nn none nn-one
  HARNESS_RUNTIME=openshell
  SKILL_PACK_SPECS=("nn=$(native_path "$HOME/src")")
  skills_openshell_prepare
  [[ -d "$(skills_root)/nn" ]]
  [[ -d "$HERMES_HOME/skills/cat/alpha" && ! -e "$HERMES_HOME/.no-bundled-skills" ]]
  ! config_lists 'skill-packs.nn.skills'
}

# Runs the real installer function (errexit on) so a stray line in it fails here.
openshell_install_bakes_packs() {
  fixture
  make_pack "$HOME/src" nn none nn-one
  HARNESS_RUNTIME=openshell
  HARNESS_LLM_MODEL=test-model
  SKILL_PACK_SPECS=("nn=$(native_path "$HOME/src")")
  ensure_openshell_cli() { :; }
  openshell_validate_shared_inference() { :; }
  metrics_check_plugin_source() { :; }
  metrics_hermes_otel_ref() { printf 'ref\n'; }
  uname() { printf 'Linux\n'; }
  openshell_resource_exists() { return 1; }
  openshell_assert_owned() { :; }
  openshell() { return 0; }
  docker() {
    printf '%s\n' "$*" >>"$ACTIONS"
    [[ -f "$(skills_openshell_context_dir)/nn/skills/nn-one/SKILL.md" ]]
  }
  install_openshell_agent
  grep -Fq 'HARNESS_SKILLS_DEFAULTS=none' "$ACTIONS"
  [[ ! -e "$(skills_openshell_context_dir)" ]]
  skills_openshell_prepare
  [[ -n "$SKILLS_OPENSHELL_HASH" && "$(skills_openshell_recorded_hash)" == "$SKILLS_OPENSHELL_HASH" ]]
  # An existing owned sandbox is kept while the pack set is unchanged.
  openshell_resource_exists() { return 0; }
  install_openshell_agent
  make_pack "$HOME/src2" oo keep oo-one
  SKILL_PACK_SPECS+=("oo=$(native_path "$HOME/src2")")
  expect_failure 'changed since sandbox' install_openshell_agent
}

run_case 'two packs coexist and removing one leaves the other' two_packs_coexist
run_case 'installed packs are read-only' installed_pack_is_read_only
run_case 're-adding a pack repairs a modified installed copy' reinstall_repairs_a_modified_pack
run_case 'cross-pack and local skill name collisions fail' cross_pack_and_local_collisions
run_case 'missing skill-name prefix warns and fails in strict mode' prefix_warns_and_strict_fails
run_case 'invalid pack ids, mismatches and layouts are rejected' pack_validation_rejects_bad_input
run_case 'remote sources need https and a SHA-256 digest' remote_sources_need_https_and_digest
run_case 'archive digest is enforced' archive_digest_is_enforced
run_case 'hostile archives are rejected' hostile_archives_are_rejected
run_case 'size limits apply to pack contents' archive_size_limits_apply
run_case 'default-skills policy follows packs and the operator override' defaults_policy_resolution
run_case 'opt-out marker exists before the Hermes install and defaults are retired after' marker_precedes_hermes_install
run_case 'an invalid pack aborts before Hermes is installed' bad_pack_aborts_before_agent_install
run_case 'retire keeps essential/modified/user skills and restore round-trips' retire_and_restore_defaults
run_case 'retirement refuses when the essential set is unknown' retirement_requires_known_essentials
run_case '--skills-purge also retires modified bundled skills' purge_retires_modified_skills
run_case 'drop-in packs are applied by sync and URL drop-ins need a digest' dropin_packs_are_applied
run_case 'drop-in permissions are checked' dropin_permissions_are_checked
run_case 'a local-skill clash fails before defaults are retired' local_clash_fails_before_retirement
run_case 'the original Hermes config is backed up once' config_backup_is_written_once
run_case 'silent retirement cases explain themselves' retirement_explains_silent_cases
run_case 'a remembered restore-defaults choice is explained' restore_defaults_choice_is_explained
run_case 'non-Hermes agents skip skill packs' non_hermes_agent_is_skipped
run_case 'no packs and no override leaves Hermes untouched' no_packs_means_no_changes
run_case 'OpenShell rejects mutating skills verbs' openshell_rejects_mutating_verbs
run_case 'OpenShell build context and pack-set hash guard' openshell_context_and_hash_guard
run_case 'OpenShell packs never touch the host Hermes' openshell_packs_do_not_touch_host_hermes
run_case 'OpenShell Hermes install bakes packs and records the hash' openshell_install_bakes_packs
finish_tests
