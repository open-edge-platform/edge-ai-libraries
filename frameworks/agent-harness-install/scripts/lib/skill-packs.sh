# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# shellcheck shell=bash
# Skill packs — generic, versioned bundles of agent skills supplied by any
# consumer (for example a VSS deployment) and layered onto Hermes without
# touching the skills Hermes manages itself.
#
# A pack is a directory or archive with pack.json + skills/<name>/SKILL.md.
# Packs are validated, installed read-only under
# ~/.agent-harness-install/skill-packs/<id>/ and wired into Hermes through
# `skills.external_dirs` in config.yaml; Hermes's own skills directory is left
# alone, so packs never mingle with (or get overwritten by) bundled skills.
# Optionally a pack asks for the bundled default skills to be retired
# ("defaults": "none"): Hermes then keeps only its essential skills, and the
# retired ones are backed up and can be restored.
#
# The structural logic lives in skill-packs.py; this file is the CLI layer,
# source resolution (directory/URL+digest/drop-in) and the Hermes adapter.
# Hermes only, on the host and in OpenShell (where packs are baked into the
# sandbox image).

# Repeatable --skills-pack values collected by main(): id=src[#sha256=hex].
SKILL_PACK_SPECS=()
SKILLS_DROPIN_DIRNAME="skill-packs.d"

# Install-flow bookkeeping (see skills_pre_agent_install).
SKILLS_REQ_ID=()
SKILLS_REQ_TYPE=()
SKILLS_REQ_REF=()
SKILLS_REQ_SHA=()
SKILLS_REQ_ORIGIN=()
SKILLS_REQ_STAGE=()
SKILLS_REQ_META=()
SKILLS_PRE_ACTIVE=""
SKILLS_PRE_EXTRA_NONE=""

skills_py() {
  command_exists python3 || error "python3 is required to manage skill packs."
  python3 "${SCRIPT_DIR}/scripts/lib/skill-packs.py" "$@"
}

skills_root() {
  printf '%s/skill-packs' "$(harness_state_root)"
}

skills_registry() {
  printf '%s/registry.json' "$(skills_root)"
}

skills_dropin_dir() {
  printf '%s/%s' "$(harness_state_root)" "$SKILLS_DROPIN_DIRNAME"
}

skills_hermes_home() {
  printf '%s' "${HERMES_HOME:-$HOME/.hermes}"
}

skills_hermes_config() {
  printf '%s' "${HERMES_CONFIG:-$(skills_hermes_home)/config.yaml}"
}

# Mutating pack operations only touch the host's Hermes outside an OpenShell run.
skills_host_apply() {
  [[ "${HARNESS_RUNTIME:-host}" != openshell ]]
}

skills_validate_id() {
  [[ "${1:-}" =~ ^[a-z0-9][a-z0-9-]{0,31}$ ]] \
    || error "Invalid skill pack id '${1:-}': use lowercase letters, digits and '-' (max 32 characters)."
}

# Creates the owner-only pack root and returns its path.
skills_prepare_root() {
  local root
  root="$(ensure_state_dir)/skill-packs"
  assert_state_path_safe "$root"
  (umask 077 && mkdir -p "$root")
  chmod 700 "$root"
  assert_owned_by_current_user "$root"
  printf '%s' "$root"
}

skills_cleanup_staging() {
  local root
  root="$(skills_root)"
  [[ -d "${root}/.staging" && ! -L "${root}/.staging" ]] || return 0
  rm -rf -- "${root}/.staging"
}

# Effective default-skills choice requested by the operator: the
# --skills-defaults flag / HARNESS_HERMES_DEFAULT_SKILLS, else the choice
# remembered by `skills restore-defaults`, else auto (follow the packs).
skills_policy_override() {
  local value="${HARNESS_HERMES_DEFAULT_SKILLS:-auto}" remembered
  if [[ "$value" == auto ]]; then
    remembered="$(skills_py registry-get --registry "$(skills_registry)" --field defaults.operator)" || remembered=""
    [[ "$remembered" == keep || "$remembered" == none ]] && value="$remembered"
  fi
  printf '%s' "$value"
}

# skills_effective_policy [extra_none] -> keep|none for the host runtime.
skills_effective_policy() {
  skills_py policy --registry "$(skills_registry)" --override "$(skills_policy_override)" \
    --runtime host ${1:+--extra-none}
}

# ---------------------------------------------------------------- sources

# skills_parse_spec 'id=src[#sha256=hex]' -> SKILLS_SPEC_{ID,SRC,SHA}
skills_parse_spec() {
  local spec="$1" rest
  [[ "$spec" == *=* ]] \
    || error "Invalid --skills-pack '${spec}': expected <id>=<directory|https-url>[#sha256=<hex>]"
  SKILLS_SPEC_ID="${spec%%=*}"
  rest="${spec#*=}"
  SKILLS_SPEC_SHA=""
  if [[ "$rest" == *"#sha256="* ]]; then
    SKILLS_SPEC_SHA="${rest##*#sha256=}"
    rest="${rest%%#sha256=*}"
  fi
  SKILLS_SPEC_SRC="$rest"
  skills_validate_id "$SKILLS_SPEC_ID"
  [[ -n "$SKILLS_SPEC_SRC" ]] || error "Invalid --skills-pack '${spec}': empty source."
}

# skills_classify_source src sha -> SKILLS_SRC_{TYPE,REF,SHA}
skills_classify_source() {
  local src="$1" sha="${2:-}"
  if [[ "$src" == *"#sha256="* ]]; then
    sha="${src##*#sha256=}"
    src="${src%%#sha256=*}"
  fi
  sha="$(printf '%s' "$sha" | tr '[:upper:]' '[:lower:]')"
  [[ -z "$sha" || "$sha" =~ ^[0-9a-f]{64}$ ]] || error "--sha256 must be 64 hexadecimal characters."
  case "$src" in
    https://*)
      SKILLS_SRC_TYPE=url
      [[ -n "$sha" ]] || error "A SHA-256 digest is required for URL pack sources (--sha256 <hex> or ...#sha256=<hex>)."
      SKILLS_SRC_REF="$src" ;;
    *://*) error "Remote skill packs must use https:// (got: ${src})." ;;
    *)
      if [[ -d "$src" ]]; then
        SKILLS_SRC_TYPE=dir
        SKILLS_SRC_REF="$(cd "$src" && pwd -P)"
        [[ -z "$sha" ]] || error "--sha256 applies to archive and URL sources, not directories."
      elif [[ -f "$src" ]]; then
        SKILLS_SRC_TYPE="file"
        SKILLS_SRC_REF="$(cd "$(dirname "$src")" && pwd -P)/$(basename "$src")"
      else
        error "Skill pack source not found: ${src}"
      fi ;;
  esac
  SKILLS_SRC_SHA="$sha"
}

# skills_fetch_archive url sha -> SKILLS_FETCHED_ARCHIVE (cached by digest)
skills_fetch_archive() {
  local url="$1" sha="$2" root cache ext dest tmp
  case "${url%%[?#]*}" in
    *.tar.gz) ext=tar.gz ;;
    *.tgz) ext=tgz ;;
    *.zip) ext=zip ;;
    *) error "Skill pack URL must end in .tar.gz, .tgz or .zip: ${url}" ;;
  esac
  root="$(skills_prepare_root)"
  cache="${root}/.cache"
  assert_state_path_safe "$cache"
  (umask 077 && mkdir -p "$cache")
  rm -f -- "${cache}"/dl.*
  dest="${cache}/${sha}.${ext}"
  if [[ -f "$dest" && ! -L "$dest" && "$(sha256_of "$dest")" == "$sha" ]]; then
    info "Using cached skill pack archive (SHA-256: ${sha:0:16}…)"
  else
    tmp="$(mktemp "${cache}/dl.XXXXXX")"
    HARNESS_FETCH_MAX_BYTES="${HARNESS_SKILLS_MAX_ARCHIVE_BYTES:-134217728}" \
      fetch_and_verify "$url" "$tmp" "Skill pack archive" "$sha"
    mv -f "$tmp" "$dest"
  fi
  SKILLS_FETCHED_ARCHIVE="$dest"
}

# True when a URL/archive pack with this exact digest is already installed.
skills_pack_unchanged() {
  local id="$1" stype="$2" ref="$3" sha="$4" registry
  [[ "$stype" == url || ( "$stype" == file && -n "$sha" ) ]] || return 1
  registry="$(skills_registry)"
  [[ "$(skills_py registry-get --registry "$registry" --field "packs.${id}.source.sha256")" == "$sha" ]] || return 1
  [[ "$(skills_py registry-get --registry "$registry" --field "packs.${id}.source.ref")" == "$ref" ]] || return 1
  local dir
  dir="$(skills_py registry-get --registry "$registry" --field "packs.${id}.dir")"
  [[ -n "$dir" && -d "$dir" ]] || return 1
  skills_py verify --registry "$registry" --id "$id" >/dev/null 2>&1
}

# skills_stage_pack id type ref sha -> SKILLS_STAGED_{DIR,META}
# Downloads (when remote), safely extracts and validates the pack into the
# staging area. Nothing outside .staging/ and .cache/ is touched.
skills_stage_pack() {
  local id="$1" stype="$2" ref="$3" sha="$4" root stage src got agents
  root="$(skills_prepare_root)"
  stage="${root}/.staging/${id}"
  assert_state_path_safe "${root}/.staging"
  (umask 077 && mkdir -p "${root}/.staging")
  rm -rf -- "$stage" "${stage}.meta.json"
  case "$stype" in
    dir) src="$ref"; sha="" ;;
    file) src="$ref" ;;
    url) skills_fetch_archive "$ref" "$sha"; src="$SKILLS_FETCHED_ARCHIVE" ;;
    *) error "Unknown skill pack source type: ${stype}" ;;
  esac
  mkdir -p "$stage"
  if ! skills_py materialize --source "$src" --out "${stage}/pack" ${sha:+--sha256 "$sha"} >"${stage}.meta.json"; then
    rm -rf -- "$stage" "${stage}.meta.json"
    error "Skill pack '${id}' did not pass validation (see the message above)."
  fi
  got="$(skills_py meta-field --meta "${stage}.meta.json" --field id)"
  [[ "$got" == "$id" ]] || error "Skill pack id mismatch: requested '${id}' but pack.json declares '${got}'."
  agents="$(skills_py meta-field --meta "${stage}.meta.json" --field agents)"
  [[ ",${agents}," == *,hermes,* ]] \
    || error "Skill pack '${id}' does not support Hermes (agents: ${agents}). Skill packs are supported for Hermes only in this release."
  SKILLS_STAGED_DIR="${stage}/pack"
  SKILLS_STAGED_META="${stage}.meta.json"
}

# True when a staged pack wants Hermes's bundled defaults retired on the host.
skills_meta_requires_none() {
  local meta="$1" defaults runtimes
  defaults="$(skills_py meta-field --meta "$meta" --field defaults)"
  runtimes="$(skills_py meta-field --meta "$meta" --field runtimes)"
  [[ "$defaults" == none && ",${runtimes}," == *,host,* ]]
}

# ------------------------------------------------- Hermes defaults policy

# skills_registry_set_defaults json — merges keys into the registry's defaults record.
skills_registry_set_defaults() {
  skills_prepare_root >/dev/null
  skills_py registry-set-defaults --registry "$(skills_registry)" --json "$1"
}

skills_ensure_marker() {
  local home marker
  home="$(skills_hermes_home)"
  safe_agent_data_dir "$home" \
    || error "Refusing to use HERMES_HOME='${home}' (not an absolute, non-symlink path distinct from \$HOME)."
  marker="${home}/.no-bundled-skills"
  if [[ ! -e "$marker" ]]; then
    (umask 077 && mkdir -p -- "$home" && : >"$marker") \
      || error "Could not create ${marker}."
    skills_registry_set_defaults '{"marker_created": true}'
    info "Hermes will keep only its essential default skills (created ${marker})."
  fi
}

# Moves Hermes's pristine bundled skills aside (full backup first). Never
# removes essential skills, locally modified skills, hub installs or skills the
# user wrote. HARNESS_SKILLS_PURGE=1 also removes modified bundled skills.
# With --dry-run nothing changes and the plan (JSON) is printed.
skills_retire_defaults() {
  local dry="" skills_dir home hermes_bin
  [[ "${1:-}" != --dry-run ]] || dry=1
  home="$(skills_hermes_home)"
  skills_dir="${home}/skills"
  if [[ ! -f "${skills_dir}/.bundled_manifest" ]]; then
    [[ -n "$dry" ]] || info "Hermes has not recorded its bundled skills yet (no .bundled_manifest), so nothing was retired. Run './install.sh skills sync' after Hermes has started once."
    return 0
  fi
  hermes_bin="$(command -v hermes 2>/dev/null || true)"
  local -a args=(--skills-dir "$skills_dir" --backup-root "$(harness_state_root)/hermes-skills-backup"
    --registry "$(skills_registry)" --hermes-home "$home")
  [[ -z "$hermes_bin" ]] || args+=(--hermes-bin "$hermes_bin")
  [[ "${HARNESS_SKILLS_PURGE:-}" != 1 ]] || args+=(--purge)
  if [[ -n "$dry" ]]; then
    skills_py retire-defaults "${args[@]}" --dry-run \
      || error "Could not work out which of Hermes's default skills would be retired; nothing was changed."
    return 0
  fi
  assert_state_path_safe "$(harness_state_root)/hermes-skills-backup"
  skills_py retire-defaults "${args[@]}" >/dev/null \
    || error "Could not retire Hermes's default skills; nothing was removed."
}

# Fails on pack-vs-pack and local-skill name clashes before anything is retired.
# Bundled skills that are about to be retired do not count as clashes.
skills_precheck_names() {
  local meta="$1" effective="${2:-keep}" local_dir="" retiring=""
  local -a also=("${@:3}")
  skills_host_apply && local_dir="$(hermes_skills_dir)"
  [[ -z "$local_dir" || -d "$local_dir" ]] || local_dir=""
  if [[ -n "$local_dir" && "$effective" == none ]]; then
    retiring="$(skills_retire_defaults --dry-run)"
  fi
  skills_py collisions --registry "$(skills_registry)" --meta "$meta" \
    ${local_dir:+--local-skills-dir "$local_dir"} ${retiring:+--retiring-json "$retiring"} \
    ${also[@]+--also-meta "${also[@]}"}
}

# Applies a `none` policy to an existing Hermes install (marker + retirement).
skills_apply_defaults() {
  local effective="$1"
  [[ "$effective" == none ]] || return 0
  if [[ "${HARNESS_HERMES_DEFAULT_SKILLS:-auto}" == none ]]; then
    skills_registry_set_defaults '{"operator": ""}'
  fi
  if [[ ! -d "$(skills_hermes_home)" ]]; then
    info "Hermes is not installed yet; the essential-only default skills will be set up when it is installed."
    return 0
  fi
  skills_ensure_marker
  skills_retire_defaults
}

# Wires every registered host pack into Hermes's config.yaml (idempotent).
skills_sync_config() {
  skills_host_apply || return 0
  local cfg line
  local -a dirs=()
  cfg="$(skills_hermes_config)"
  while IFS= read -r line; do
    [[ -z "$line" ]] || dirs+=("$line")
  done < <(skills_py pack-dirs --registry "$(skills_registry)" --runtime host)
  ((${#dirs[@]} > 0)) || return 0
  if [[ ! -f "$cfg" ]]; then
    info "Hermes config not found (${cfg}); skill packs will be wired in once Hermes is installed."
    return 0
  fi
  with_state_lock hermes-config skills_py merge-config --config "$cfg" --add "${dirs[@]}" >/dev/null \
    || error "Could not update skills.external_dirs in ${cfg}."
}

# ------------------------------------------------------------ pack commit

# skills_commit_pack id stage meta type ref sha origin
skills_commit_pack() {
  local id="$1" stage="$2" meta="$3" stype="$4" ref="$5" sha="$6" origin="$7"
  local root registry hash old_hash version skills local_dir=""
  root="$(skills_prepare_root)"
  registry="${root}/registry.json"
  hash="$(skills_py meta-field --meta "$meta" --field hash)"
  skills="$(skills_py meta-field --meta "$meta" --field skills)"
  old_hash="$(skills_py registry-get --registry "$registry" --field "packs.${id}.hash")"
  if [[ "$old_hash" == "$hash" && -d "${root}/${id}" ]]; then
    if skills_py verify --registry "$registry" --id "$id" >/dev/null 2>&1; then
      info "Skill pack '${id}' is unchanged (${hash:0:12})."
      return 0
    fi
    warn "Installed skill pack '${id}' no longer matches its registered content; reinstalling it."
  fi
  skills_host_apply && local_dir="$(hermes_skills_dir)"
  skills_py collisions --registry "$registry" --meta "$meta" ${local_dir:+--local-skills-dir "$local_dir"} \
    || error "Skill pack '${id}' was not installed."
  assert_state_path_safe "${root}/${id}"
  skills_py install --staged "$stage" --dest "${root}/${id}" \
    || error "Could not install skill pack '${id}'."
  skills_py registry-add --registry "$registry" --meta "$meta" --source-type "$stype" \
    --source-ref "$ref" ${sha:+--source-sha256 "$sha"} --dir "${root}/${id}" --origin "$origin" \
    || error "Could not record skill pack '${id}' in the registry."
  version="$(skills_py meta-field --meta "$meta" --field version)"
  ok "Skill pack '${id}' ${version} installed (skills: ${skills//,/, })."
}

# skills_add_pack id type ref sha origin — stage, commit and wire one pack.
skills_add_pack() {
  local id="$1" stype="$2" ref="$3" sha="$4" origin="$5" extra="" effective
  skills_validate_id "$id"
  if skills_pack_unchanged "$id" "$stype" "$ref" "$sha"; then
    info "Skill pack '${id}' is already installed from the same source."
    if skills_host_apply; then
      skills_apply_defaults "$(skills_effective_policy)"
    fi
  else
    skills_stage_pack "$id" "$stype" "$ref" "$sha"
    if skills_host_apply; then
      skills_meta_requires_none "$SKILLS_STAGED_META" && extra=1
      effective="$(skills_effective_policy "$extra")"
      skills_precheck_names "$SKILLS_STAGED_META" "$effective" \
        || error "Skill pack '${id}' was not installed."
      if [[ -n "$extra" && "$effective" != none ]]; then
        info "Skill pack '${id}' asks for essential-only default skills, but the default-skills choice is 'keep' (--skills-defaults or an earlier 'skills restore-defaults'). Pass --skills-defaults none to retire them."
      fi
      # Retire first so bundled skills do not collide with the pack's own.
      skills_apply_defaults "$effective"
    else
      skills_precheck_names "$SKILLS_STAGED_META" \
        || error "Skill pack '${id}' was not installed."
    fi
    skills_commit_pack "$id" "$SKILLS_STAGED_DIR" "$SKILLS_STAGED_META" "$stype" "$ref" "$sha" "$origin"
  fi
  skills_sync_config
  skills_cleanup_staging
}

# ------------------------------------------------------------- drop-ins

# skills_read_dropins -> SKILLS_DROPIN_LINES (one TSV record per drop-in)
skills_read_dropins() {
  local dir out
  dir="$(skills_dropin_dir)"
  SKILLS_DROPIN_LINES=()
  [[ -e "$dir" || -L "$dir" ]] || return 0
  out="$(skills_py dropins --dir "$dir")" || error "Invalid skill pack drop-in configuration in ${dir}."
  [[ -z "$out" ]] || mapfile -t SKILLS_DROPIN_LINES <<<"$out"
}

skills_process_dropins() {
  local line id stype ref sha file
  skills_read_dropins
  for line in ${SKILLS_DROPIN_LINES[@]+"${SKILLS_DROPIN_LINES[@]}"}; do
    IFS=$'\t' read -r id stype ref sha file <<<"$line"
    [[ "$sha" != - ]] || sha=""
    info "Skill pack drop-in: ${file}"
    skills_add_pack "$id" "$stype" "$ref" "$sha" dropin
  done
}

# ---------------------------------------------------------- CLI commands

skills_cmd_add() {
  local id="" src="" sha=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --sha256) [[ -n "${2:-}" ]] || error "--sha256 requires a value."; sha="$2"; shift ;;
      --sha256=*) sha="${1#*=}" ;;
      -*) error "Unknown option for 'skills add': $1" ;;
      *)
        if [[ -z "$id" ]]; then id="$1"
        elif [[ -z "$src" ]]; then src="$1"
        else error "Too many arguments for 'skills add'."; fi ;;
    esac
    shift
  done
  [[ -n "$id" && -n "$src" ]] || error "Usage: ./install.sh skills add <id> <directory|https-url> [--sha256 <hex>]"
  skills_validate_id "$id"
  skills_classify_source "$src" "$sha"
  skills_add_pack "$id" "$SKILLS_SRC_TYPE" "$SKILLS_SRC_REF" "$SKILLS_SRC_SHA" cli
}

skills_cmd_remove() {
  local id="${1:-}" registry dir cfg
  [[ -n "$id" ]] || error "Usage: ./install.sh skills remove <id>"
  skills_validate_id "$id"
  registry="$(skills_registry)"
  dir="$(skills_py registry-get --registry "$registry" --field "packs.${id}.dir")"
  [[ -n "$dir" ]] || error "Skill pack '${id}' is not registered."
  cfg="$(skills_hermes_config)"
  if skills_host_apply && [[ -f "$cfg" ]]; then
    with_state_lock hermes-config skills_py merge-config --config "$cfg" --remove "${dir}/skills" >/dev/null \
      || error "Could not update skills.external_dirs in ${cfg}; the pack was not removed."
  fi
  skills_py registry-remove --registry "$registry" --id "$id"
  skills_py remove-dir --path "$dir" --within "$(skills_root)" || warn "Could not delete ${dir}; remove it manually."
  ok "Skill pack '${id}' removed."
  if [[ "$(skills_py registry-get --registry "$registry" --field defaults.marker_created)" == true \
    && "$(skills_effective_policy)" != none ]]; then
    info "Hermes's default skills stay retired. Run './install.sh skills restore-defaults' to bring them back."
  fi
}

skills_cmd_list() {
  skills_py list --registry "$(skills_registry)" --hermes-home "$(skills_hermes_home)"
  skills_read_dropins
  ((${#SKILLS_DROPIN_LINES[@]} == 0)) \
    || info "${#SKILLS_DROPIN_LINES[@]} drop-in pack definition(s) in $(skills_dropin_dir) (applied by install and 'skills sync')."
  if [[ "${HARNESS_RUNTIME:-host}" == openshell ]]; then
    skills_openshell_report 0
  fi
}

skills_cmd_verify() {
  local id="${1:-}"
  local -a args=(--registry "$(skills_registry)")
  [[ -z "$id" ]] || args+=(--id "$id")
  if skills_host_apply; then
    args+=(--config "$(skills_hermes_config)" --hermes-home "$(skills_hermes_home)" --override "$(skills_policy_override)")
  fi
  skills_py verify "${args[@]}" || error "Skill pack verification failed."
  if [[ "${HARNESS_RUNTIME:-host}" == openshell ]]; then
    skills_openshell_report 1
  fi
}

skills_cmd_sync() {
  skills_process_dropins
  skills_apply_defaults "$(skills_effective_policy)"
  skills_sync_config
  skills_cleanup_staging
  ok "Skill packs are in sync."
}

skills_cmd_restore_defaults() {
  local home
  home="$(skills_hermes_home)"
  [[ -d "${home}/skills" ]] || error "No Hermes skills directory at ${home}/skills; nothing to restore."
  skills_py restore-defaults --registry "$(skills_registry)" --skills-dir "${home}/skills" --hermes-home "$home" \
    || error "Could not restore Hermes's default skills."
  ok "Hermes's default skills restored."
  if [[ "$(skills_py policy --registry "$(skills_registry)" --override auto --runtime host)" == none ]]; then
    info "Registered packs still request essential-only defaults; they will not be retired again until you run './install.sh skills sync --skills-defaults none'."
  fi
}

# run_skills_command <verb> [args…] — Hermes skill packs (plural; the singular
# `skill` command manages single skills).
run_skills_command() {
  local verb="${1:-}"
  [[ -n "$verb" ]] || { usage; error "skills requires a verb (add/remove/list/verify/sync/restore-defaults)."; }
  shift
  if [[ -n "${HARNESS_AGENT:-}" && "$(canonical_agent_name "$HARNESS_AGENT")" != hermes ]]; then
    info "Skill packs are supported for Hermes only in this release; nothing to do for ${HARNESS_AGENT}."
    return 0
  fi
  if [[ "${HARNESS_RUNTIME:-host}" == openshell ]]; then
    # Skill packs are Hermes-only; select the Hermes sandbox profile when --harness is omitted.
    HARNESS_AGENT=hermes
    case "$verb" in
      list | verify) ;;
      add | remove | sync | restore-defaults)
        error "Skill packs for an OpenShell sandbox are baked into its image: register packs without --runtime openshell (./install.sh skills add …) or pass --skills-pack, then remove and recreate the sandbox (./uninstall.sh --runtime openshell --harness hermes --sandbox-only, then ./install.sh --runtime openshell --harness hermes)." ;;
    esac
  fi
  case "$verb" in
    add) skills_cmd_add "$@" ;;
    remove) skills_cmd_remove "$@" ;;
    list) skills_cmd_list ;;
    verify) skills_cmd_verify "$@" ;;
    sync) skills_cmd_sync ;;
    restore-defaults) skills_cmd_restore_defaults ;;
    *) usage; error "Unknown skills verb: ${verb}" ;;
  esac
}

# --------------------------------------------------- host install hooks

# skills_collect_requests — --skills-pack flags first, then drop-ins.
skills_collect_requests() {
  local spec line id stype ref sha file i dup
  SKILLS_REQ_ID=(); SKILLS_REQ_TYPE=(); SKILLS_REQ_REF=(); SKILLS_REQ_SHA=()
  SKILLS_REQ_ORIGIN=(); SKILLS_REQ_STAGE=(); SKILLS_REQ_META=()
  for spec in ${SKILL_PACK_SPECS[@]+"${SKILL_PACK_SPECS[@]}"}; do
    skills_parse_spec "$spec"
    skills_classify_source "$SKILLS_SPEC_SRC" "$SKILLS_SPEC_SHA"
    for id in ${SKILLS_REQ_ID[@]+"${SKILLS_REQ_ID[@]}"}; do
      [[ "$id" != "$SKILLS_SPEC_ID" ]] || error "--skills-pack '${SKILLS_SPEC_ID}' was given more than once."
    done
    SKILLS_REQ_ID+=("$SKILLS_SPEC_ID"); SKILLS_REQ_TYPE+=("$SKILLS_SRC_TYPE")
    SKILLS_REQ_REF+=("$SKILLS_SRC_REF"); SKILLS_REQ_SHA+=("$SKILLS_SRC_SHA"); SKILLS_REQ_ORIGIN+=(flag)
  done
  skills_read_dropins
  for line in ${SKILLS_DROPIN_LINES[@]+"${SKILLS_DROPIN_LINES[@]}"}; do
    IFS=$'\t' read -r id stype ref sha file <<<"$line"
    [[ "$sha" != - ]] || sha=""
    dup=""
    for ((i = 0; i < ${#SKILLS_REQ_ID[@]}; i++)); do
      [[ "${SKILLS_REQ_ID[$i]}" != "$id" ]] || dup=1
    done
    if [[ -n "$dup" ]]; then
      info "Skill pack '${id}' is given by --skills-pack; ignoring drop-in ${file}."
      continue
    fi
    SKILLS_REQ_ID+=("$id"); SKILLS_REQ_TYPE+=("$stype"); SKILLS_REQ_REF+=("$ref")
    SKILLS_REQ_SHA+=("$sha"); SKILLS_REQ_ORIGIN+=(dropin)
  done
}

# skills_pre_agent_install — before install_selected_agent. Validates and
# stages every requested pack (a bad pack aborts before Hermes is touched) and
# creates the opt-out marker ahead of the Hermes installer, so its first
# bundled-skill sync only seeds the essential skills.
skills_pre_agent_install() {
  local agent i extra="" effective has_registered
  SKILLS_PRE_ACTIVE=""
  SKILLS_PRE_EXTRA_NONE=""
  agent="$(canonical_agent_name "${HARNESS_AGENT:-openclaw}")"
  if [[ "$agent" != hermes ]]; then
    ((${#SKILL_PACK_SPECS[@]} == 0)) \
      || warn "Skill packs are supported for Hermes only in this release; ignoring --skills-pack for ${agent}."
    return 0
  fi
  skills_collect_requests
  has_registered="$(skills_py has-packs --registry "$(skills_registry)" --runtime host)"
  if ((${#SKILLS_REQ_ID[@]} == 0)) && [[ "$has_registered" != true && "${HARNESS_HERMES_DEFAULT_SKILLS:-auto}" != none ]]; then
    return 0
  fi
  SKILLS_PRE_ACTIVE=1
  for ((i = 0; i < ${#SKILLS_REQ_ID[@]}; i++)); do
    if skills_pack_unchanged "${SKILLS_REQ_ID[$i]}" "${SKILLS_REQ_TYPE[$i]}" "${SKILLS_REQ_REF[$i]}" "${SKILLS_REQ_SHA[$i]}"; then
      info "Skill pack '${SKILLS_REQ_ID[$i]}' is already installed from the same source."
      continue
    fi
    skills_stage_pack "${SKILLS_REQ_ID[$i]}" "${SKILLS_REQ_TYPE[$i]}" "${SKILLS_REQ_REF[$i]}" "${SKILLS_REQ_SHA[$i]}"
    SKILLS_REQ_STAGE[i]="$SKILLS_STAGED_DIR"
    SKILLS_REQ_META[i]="$SKILLS_STAGED_META"
    ! skills_meta_requires_none "$SKILLS_STAGED_META" || extra=1
  done
  SKILLS_PRE_EXTRA_NONE="$extra"
  effective="$(skills_effective_policy "$extra")"
  # Reject name clashes (registry, local skills, other requested packs) before the marker or Hermes install changes anything.
  local -a staged=()
  for ((i = 0; i < ${#SKILLS_REQ_ID[@]}; i++)); do
    [[ -z "${SKILLS_REQ_META[$i]:-}" ]] || staged+=("${SKILLS_REQ_META[$i]}")
  done
  for ((i = 0; i < ${#SKILLS_REQ_ID[@]}; i++)); do
    [[ -n "${SKILLS_REQ_META[$i]:-}" ]] || continue
    skills_precheck_names "${SKILLS_REQ_META[$i]}" "$effective" "${staged[@]}" \
      || error "Skill pack '${SKILLS_REQ_ID[$i]}' was not installed."
  done
  if [[ "$effective" == none ]]; then
    skills_ensure_marker
  fi
}

# skills_post_agent_install — after install_selected_agent: retire any
# already-seeded defaults, install the staged packs and wire them into Hermes.
skills_post_agent_install() {
  local i
  [[ -n "$SKILLS_PRE_ACTIVE" ]] || return 0
  skills_apply_defaults "$(skills_effective_policy "$SKILLS_PRE_EXTRA_NONE")"
  for ((i = 0; i < ${#SKILLS_REQ_ID[@]}; i++)); do
    [[ -n "${SKILLS_REQ_STAGE[$i]:-}" ]] || continue
    skills_commit_pack "${SKILLS_REQ_ID[$i]}" "${SKILLS_REQ_STAGE[$i]}" "${SKILLS_REQ_META[$i]}" \
      "${SKILLS_REQ_TYPE[$i]}" "${SKILLS_REQ_REF[$i]}" "${SKILLS_REQ_SHA[$i]}" "${SKILLS_REQ_ORIGIN[$i]}"
  done
  skills_sync_config
  skills_cleanup_staging
  SKILLS_PRE_ACTIVE=""
}

# ------------------------------------------------------------- OpenShell

skills_openshell_context_dir() {
  printf '%s/openshell/skill-packs' "$SCRIPT_DIR"
}

# skills_openshell_prepare — registers requested packs (no host changes) and
# computes SKILLS_OPENSHELL_{HASH,DEFAULTS} for the sandbox image.
skills_openshell_prepare() {
  local override="${HARNESS_HERMES_DEFAULT_SKILLS:-auto}" registry spec
  skills_prepare_root >/dev/null
  registry="$(skills_registry)"
  for spec in ${SKILL_PACK_SPECS[@]+"${SKILL_PACK_SPECS[@]}"}; do
    skills_parse_spec "$spec"
    skills_classify_source "$SKILLS_SPEC_SRC" "$SKILLS_SPEC_SHA"
    skills_add_pack "$SKILLS_SPEC_ID" "$SKILLS_SRC_TYPE" "$SKILLS_SRC_REF" "$SKILLS_SRC_SHA" flag
  done
  skills_process_dropins
  # shellcheck disable=SC2034  # consumed by scripts/lib/openshell.sh
  SKILLS_OPENSHELL_HASH="$(skills_py pack-set-hash --registry "$registry" --runtime openshell --override "$override")"
  # shellcheck disable=SC2034
  SKILLS_OPENSHELL_DEFAULTS="$(skills_py policy --registry "$registry" --runtime openshell --override "$override")"
}

skills_openshell_recorded_hash() {
  local file
  file="$(openshell_profile_dir)/profile.json"
  [[ -f "$file" ]] || return 0
  node -e 'const p = JSON.parse(require("node:fs").readFileSync(process.argv[1], "utf8")); process.stdout.write(typeof p.skills === "string" ? p.skills : "");' "$file"
}

# Records the skill-pack set an owned sandbox was built with.
skills_openshell_record_hash() {
  local hash="$1" dir file profile
  dir="$(openshell_profile_dir)"
  file="${dir}/profile.json"
  [[ -f "$file" ]] || return 0
  [[ -n "$hash" || -n "$(skills_openshell_recorded_hash)" ]] || return 0
  profile="$(node -e 'const p = JSON.parse(require("node:fs").readFileSync(process.argv[1], "utf8")); p.skills = process.argv[2]; console.log(JSON.stringify(p));' "$file" "$hash")" \
    || error "Could not update the OpenShell profile."
  atomic_write_file "$file" "$profile"
}

# An existing sandbox keeps the skills it was built with; refuse to silently
# diverge from the registered packs.
skills_openshell_assert_unchanged() {
  local desired="$1" recorded
  recorded="$(skills_openshell_recorded_hash)"
  [[ "$recorded" == "$desired" ]] && return 0
  error "The skill packs (or default-skills policy) changed since sandbox ${OPENSHELL_NAME} was created, and its skills are fixed in its image.
Recreate it to apply them:
  ./uninstall.sh --runtime openshell --harness hermes --sandbox-only --yes
  ./install.sh --runtime openshell --harness hermes ..."
}

# skills_openshell_report strict — compares the registry with the sandbox.
skills_openshell_report() {
  local strict="$1" desired recorded override="${HARNESS_HERMES_DEFAULT_SKILLS:-auto}"
  [[ -f "$(openshell_profile_dir)/profile.json" ]] || { info "No OpenShell sandbox is provisioned for this agent yet."; return 0; }
  desired="$(skills_py pack-set-hash --registry "$(skills_registry)" --runtime openshell --override "$override")"
  recorded="$(skills_openshell_recorded_hash)"
  if [[ "$desired" == "$recorded" ]]; then
    ok "The OpenShell sandbox image matches the registered skill packs."
  elif [[ "$strict" == 1 ]]; then
    error "The registered skill packs differ from the ones baked into the OpenShell sandbox; recreate the sandbox to apply them."
  else
    warn "The registered skill packs differ from the ones baked into the OpenShell sandbox; recreate the sandbox to apply them."
  fi
}

# The directory ships with an empty manifest.json (tracked in git) so that
# `docker build` of openshell/Dockerfile works without any staged packs.
skills_openshell_write_empty_context() {
  local dir="$1"
  rm -rf -- "$dir"
  mkdir -p "$dir"
  printf '{"schema":1,"defaults":"keep","packs":[]}\n' >"${dir}/manifest.json"
}

# skills_openshell_stage_context agent — fills the docker build context
# (always creates manifest.json so the directory exists for COPY).
skills_openshell_stage_context() {
  local agent="$1" dir
  dir="$(skills_openshell_context_dir)"
  if [[ "$agent" == hermes ]]; then
    skills_py stage-context --registry "$(skills_registry)" --out "$dir" --runtime openshell \
      --override "${HARNESS_HERMES_DEFAULT_SKILLS:-auto}" >/dev/null \
      || error "Could not stage skill packs for the sandbox image."
  else
    skills_openshell_write_empty_context "$dir"
  fi
}

skills_openshell_clean_context() {
  local dir
  dir="$(skills_openshell_context_dir)"
  [[ -d "$dir" && ! -L "$dir" ]] || return 0
  skills_openshell_write_empty_context "$dir"
}
