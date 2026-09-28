# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# shellcheck shell=bash
# Sandbox/gateway manager — each "sandbox" is a container with Intel GPU
# device passthrough; state is tracked in a JSON registry under the state
# directory. There is no CDI step here — Intel render nodes pass straight
# through via --device.

HARNESS_SANDBOX_PREFIX="${HARNESS_SANDBOX_PREFIX:-iplat}"
HARNESS_DEFAULT_SANDBOX_PORT="${HARNESS_DEFAULT_SANDBOX_PORT:-7860}"

# Pure path computation -- does not create the state dir, so a read-only
# caller (status, sandbox list) doesn't have the side effect of creating
# ~/.intel-agent. Writers go through with_state_lock, which already creates
# the state dir itself for the lock file.
sandbox_registry_file() {
  printf '%s/sandboxes.json' "$(harness_state_root)"
}

# Verifies a registry file is safe to read before any raw access to it.
assert_registry_readable() {
  local reg_file="$1"
  assert_state_path_safe "$reg_file"
  assert_owned_by_current_user "$reg_file"
}

sandbox_registry_set_entry() {
  local name="$1" json_entry="$2"
  with_state_lock sandbox-registry _sandbox_registry_set_entry_locked "$name" "$json_entry"
}

_sandbox_registry_set_entry_locked() {
  local name="$1" json_entry="$2" reg_file tmp
  reg_file="$(sandbox_registry_file)"
  assert_state_path_safe "$reg_file"
  [[ ! -e "$reg_file" ]] || assert_owned_by_current_user "$reg_file"
  tmp="$(mktemp)"
  node -e '
    const fs = require("node:fs");
    const [regFile, name] = process.argv.slice(1);
    const entryJson = fs.readFileSync(0, "utf8");
    let registry = {};
    try { registry = JSON.parse(fs.readFileSync(regFile, "utf8")); } catch {}
    registry[name] = JSON.parse(entryJson);
    process.stdout.write(JSON.stringify(registry, null, 2));
  ' "$reg_file" "$name" <<<"$json_entry" >"$tmp" || { rm -f "$tmp"; error "Could not update sandbox registry."; }
  chmod 600 "$tmp"
  mv -f "$tmp" "$reg_file"
  assert_state_path_safe "$reg_file"
  assert_owned_by_current_user "$reg_file"
}

sandbox_registry_remove_entry() {
  local name="$1"
  [[ -f "$(sandbox_registry_file)" ]] || return 0
  with_state_lock sandbox-registry _sandbox_registry_remove_entry_locked "$name"
}

_sandbox_registry_remove_entry_locked() {
  local name="$1" reg_file tmp
  reg_file="$(sandbox_registry_file)"
  [[ -f "$reg_file" ]] || return 0
  assert_state_path_safe "$reg_file"
  assert_owned_by_current_user "$reg_file"
  tmp="$(mktemp)"
  node -e '
    const fs = require("node:fs");
    const [regFile, name] = process.argv.slice(1);
    let registry = {};
    try { registry = JSON.parse(fs.readFileSync(regFile, "utf8")); } catch {}
    delete registry[name];
    process.stdout.write(JSON.stringify(registry, null, 2));
  ' "$reg_file" "$name" >"$tmp"
  chmod 600 "$tmp"
  mv -f "$tmp" "$reg_file"
  assert_state_path_safe "$reg_file"
  assert_owned_by_current_user "$reg_file"
}

# sandbox_registry_set_status name status — patches just the status field,
# used by start_sandbox/stop_sandbox so `sandbox list` doesn't keep showing
# "running" for a container that was actually stopped (or vice versa).
sandbox_registry_set_status() {
  local name="$1" status="$2"
  with_state_lock sandbox-registry _sandbox_registry_set_status_locked "$name" "$status"
}

_sandbox_registry_set_status_locked() {
  local name="$1" status="$2" reg_file tmp
  reg_file="$(sandbox_registry_file)"
  [[ -f "$reg_file" ]] || return 0
  assert_state_path_safe "$reg_file"
  assert_owned_by_current_user "$reg_file"
  tmp="$(mktemp)"
  node -e '
    const fs = require("node:fs");
    const [regFile, name, status] = process.argv.slice(1);
    let registry = {};
    try { registry = JSON.parse(fs.readFileSync(regFile, "utf8")); } catch {}
    if (registry[name]) registry[name].status = status;
    process.stdout.write(JSON.stringify(registry, null, 2));
  ' "$reg_file" "$name" "$status" >"$tmp" || { rm -f "$tmp"; return 1; }
  chmod 600 "$tmp"
  mv -f "$tmp" "$reg_file"
  assert_state_path_safe "$reg_file"
  assert_owned_by_current_user "$reg_file"
}

sandbox_registry_field() {
  local name="$1" field="$2" reg_file
  reg_file="$(sandbox_registry_file)"
  [[ -f "$reg_file" ]] || return 1
  assert_state_path_safe "$reg_file"
  assert_owned_by_current_user "$reg_file"
  node -e '
    try {
      const r = JSON.parse(require("node:fs").readFileSync(process.argv[1], "utf8"));
      const v = r[process.argv[2]]?.[process.argv[3]];
      if (v !== undefined) process.stdout.write(String(v));
    } catch {}
  ' "$reg_file" "$name" "$field"
}

sandbox_container_name() {
  printf '%s-%s' "$HARNESS_SANDBOX_PREFIX" "$1"
}

# Sandbox name: lowercase letters/digits/single hyphens, 2-40 chars.
validate_sandbox_name() {
  local name="$1"
  [[ "$name" =~ ^[a-z][a-z0-9-]{0,38}[a-z0-9]$ && "$name" != *--* ]]
}

resolve_gateway_port() {
  local port="${HARNESS_SANDBOX_PORT:-$HARNESS_DEFAULT_SANDBOX_PORT}"
  [[ "$port" =~ ^[0-9]+$ ]] && ((port >= 1024 && port <= 65535)) \
    || error "HARNESS_SANDBOX_PORT must be an integer between 1024 and 65535."
  printf '%s' "$port"
}

# Best-effort local listener check; fails open (assumes free) if neither
# tool is present, since that mirrors what `docker run -p` itself would do.
port_is_available() {
  local port="$1"
  if command_exists ss; then
    ! ss -H -t -l -n "sport = :${port}" 2>/dev/null | grep -q .
  elif command_exists lsof; then
    ! lsof -nP -iTCP:"${port}" -sTCP:LISTEN -t >/dev/null 2>&1
  else
    return 0
  fi
}

# Only auto-picks an alternate port when HARNESS_SANDBOX_PORT wasn't set
# explicitly — an explicit request that collides should fail loudly instead.
resolve_available_gateway_port() {
  local port candidate
  port="$(resolve_gateway_port)"
  if port_is_available "$port"; then
    printf '%s' "$port"
    return 0
  fi
  if [[ -n "${HARNESS_SANDBOX_PORT:-}" ]]; then
    error "Port ${port} (HARNESS_SANDBOX_PORT) is already in use. Choose a different
port or stop whatever is listening on it."
  fi
  for candidate in $(seq $((port + 1)) $((port + 20))); do
    if [[ "$candidate" -le 65535 ]] && port_is_available "$candidate"; then
      warn "Port ${port} is in use; automatically selected ${candidate} instead."
      printf '%s' "$candidate"
      return 0
    fi
  done
  error "Could not find a free port near ${port}. Set HARNESS_SANDBOX_PORT explicitly."
}

sandbox_exists() {
  docker inspect "$(sandbox_container_name "$1")" >/dev/null 2>&1
}

sandbox_running() {
  [[ "$(docker inspect -f '{{.State.Running}}' "$(sandbox_container_name "$1")" 2>/dev/null)" == "true" ]]
}

# Loose defense-in-depth check — docker treats the image as a single argv
# entry so shell injection isn't the risk here, but a malformed reference is
# still worth rejecting before it reaches `docker run`.
validate_image_reference() {
  local image="$1"
  [[ "$image" =~ ^[A-Za-z0-9]([A-Za-z0-9._/:-]*[A-Za-z0-9])?(@sha256:[0-9a-fA-F]{64})?$ ]] \
    || error "Invalid image reference: ${image}"
}

# create_sandbox name image [port_spec] [env_pairs]
# port_spec is either "PORT" (host and container port match) or
# "HOST:CONTAINER" for images with a fixed internal listen port. Ignored for
# host publishing when HARNESS_GATEWAY_ENABLED=1 — the container port is
# still used as the gateway's proxy target either way.
# env_pairs: space-separated KEY=VALUE tokens forwarded as -e KEY=VALUE to
# docker run (e.g. to parameterize a generic edge-microservice image).
create_sandbox() {
  local name="$1" image="$2" port_spec="${3:-}" env_pairs="${4:-}" container gpu_args entry
  local host_port container_port use_gateway
  validate_sandbox_name "$name" || error "Sandbox name '$name' must be lowercase
letters/digits/hyphens, start/end alphanumeric, no consecutive hyphens."
  [[ -n "$image" ]] || error "create_sandbox requires an image (set HARNESS_SANDBOX_IMAGE)."
  validate_image_reference "$image"
  container="$(sandbox_container_name "$name")"
  use_gateway="$(sandbox_gateway_enabled && printf 1 || printf 0)"
  if [[ "$port_spec" == *:* ]]; then
    host_port="${port_spec%%:*}"
    container_port="${port_spec##*:}"
  elif [[ "$use_gateway" == "1" ]]; then
    # Gateway mode never publishes a host port, so there's nothing to check
    # host-side availability against — just pick the logical target port.
    host_port="${port_spec:-$HARNESS_DEFAULT_SANDBOX_PORT}"
    container_port="$host_port"
  else
    host_port="${port_spec:-$(resolve_available_gateway_port)}"
    container_port="$host_port"
  fi
  sandbox_exists "$name" && error "Sandbox '$name' already exists. Destroy it first, or
choose another name."

  local -a env_args=()
  docker_proxy_env_args_into env_args
  local pair
  for pair in $env_pairs; do
    [[ "$pair" == *=* ]] || error "Invalid env pair (expected KEY=VALUE): ${pair}"
    env_args+=(-e "$pair")
  done

  gpu_args="$(intel_gpu_docker_device_args)"
  if [[ "$use_gateway" == "1" ]]; then
    ensure_gateway_running
    info "Creating sandbox '${name}' from ${image} behind the harness gateway…"
    # shellcheck disable=SC2086
    docker run -d --name "$container" --restart unless-stopped \
      --network "$HARNESS_GATEWAY_NETWORK" "${env_args[@]}" $gpu_args "$image" \
      || error "Could not start container for sandbox '${name}'."
    gateway_set_route "$name" "http://${container}:${container_port}"
  else
    info "Creating sandbox '${name}' from ${image} on port ${host_port}…"
    # shellcheck disable=SC2086
    docker run -d --name "$container" --restart unless-stopped \
      -p "$(resolve_bind_host):${host_port}:${container_port}" "${env_args[@]}" $gpu_args "$image" \
      || error "Could not start container for sandbox '${name}'."
  fi

  entry="$(node -e '
    process.stdout.write(JSON.stringify({
      image: process.argv[1], port: Number(process.argv[2]),
      containerPort: process.argv[2] === process.argv[3] ? undefined : Number(process.argv[3]),
      createdAt: new Date().toISOString(), status: "running",
      env: process.argv[4] ? process.argv[4].split(" ").filter(Boolean) : [],
      gatewayManaged: process.argv[5] === "1",
    }));
  ' "$image" "$host_port" "$container_port" "$env_pairs" "$use_gateway")"
  sandbox_registry_set_entry "$name" "$entry"
  if [[ "$use_gateway" == "1" ]]; then
    ok "Sandbox '${name}' is running behind the gateway: $(gateway_route_url "$name")"
  else
    ok "Sandbox '${name}' is running on port ${host_port}"
  fi
}

start_sandbox() {
  local name="$1"
  sandbox_exists "$name" || error "Sandbox '$name' is not registered."
  docker start "$(sandbox_container_name "$name")" >/dev/null || error "Could not start sandbox '$name'."
  sandbox_registry_set_status "$name" running
  ok "Sandbox '${name}' started"
}

stop_sandbox() {
  local name="$1"
  sandbox_exists "$name" || error "Sandbox '$name' is not registered."
  docker stop "$(sandbox_container_name "$name")" >/dev/null || error "Could not stop sandbox '$name'."
  sandbox_registry_set_status "$name" stopped
  ok "Sandbox '${name}' stopped"
}

destroy_sandbox() {
  local name="$1" force="${2:-}" container
  container="$(sandbox_container_name "$name")"
  if sandbox_exists "$name"; then
    if ! docker rm -f "$container" >/dev/null 2>&1; then
      # --force only tolerates a removal failure when the container turns
      # out to already be gone (e.g. a race) -- a genuine removal failure
      # must not silently drop the registry entry for a still-running
      # container, regardless of --force.
      if [[ "$force" != "--force" ]] || docker inspect "$container" >/dev/null 2>&1; then
        error "Could not remove container for '$name'."
      fi
    fi
  fi
  gateway_remove_route "$name"
  sandbox_registry_remove_entry "$name"
  ok "Sandbox '${name}' destroyed"
}

list_sandboxes() {
  local reg_file out
  reg_file="$(sandbox_registry_file)"
  [[ -f "$reg_file" ]] || { info "No sandboxes registered."; return 0; }
  assert_registry_readable "$reg_file"
  out="$(node -e '
    const registry = JSON.parse(require("node:fs").readFileSync(process.argv[1], "utf8"));
    const gatewayPort = process.argv[2];
    const advertisedHost = process.argv[3];
    for (const name of Object.keys(registry)) {
      const e = registry[name];
      const portInfo = e.gatewayManaged
        ? `gateway->http://${advertisedHost}:${gatewayPort}/${name}`
        : (e.containerPort ? `${e.port}->${e.containerPort}` : e.port);
      console.log(`  ${name}\tport=${portInfo}\timage=${e.image}\tstatus=${e.status}`);
    }
  ' "$reg_file" "$(resolve_gateway_port_for_display)" "$(resolve_advertised_host)")"
  # Same message whether the registry file is absent or just empty.
  if [[ -n "$out" ]]; then
    printf '%s\n' "$out"
  else
    info "No sandboxes registered."
  fi
}

# connect_sandbox name — opens an interactive shell inside a running
# sandbox, trying bash first and falling back to sh.
connect_sandbox() {
  local name="$1" container shell
  [[ -n "$name" ]] || error "connect requires a sandbox name."
  sandbox_exists "$name" || error "Sandbox '$name' is not registered."
  sandbox_running "$name" || error "Sandbox '$name' is not running. Start it first:
./install.sh sandbox start $name"
  container="$(sandbox_container_name "$name")"
  for shell in bash sh; do
    if docker exec "$container" "$shell" -c 'exit 0' >/dev/null 2>&1; then
      info "Connecting to '${name}' (${shell})…"
      exec docker exec -it "$container" "$shell"
    fi
  done
  error "No usable shell (bash or sh) found inside '${name}'."
}

# backup_sandbox name — commits the running container to a tagged image so it
# can be recreated even after the container is removed.
backup_sandbox() {
  local name="$1" container tag
  container="$(sandbox_container_name "$name")"
  sandbox_exists "$name" || error "Sandbox '$name' is not registered; nothing to back up."
  tag="${container}-backup-$(date -u +%Y%m%dT%H%M%SZ)"
  info "Backing up sandbox '${name}' to image ${tag}…"
  docker commit "$container" "$tag" >/dev/null || error "Backup failed for sandbox '$name'."
  ok "Backed up '${name}' -> ${tag}"
  printf '%s' "$tag"
}

backup_all_sandboxes() {
  local reg_file names name failures=0
  reg_file="$(sandbox_registry_file)"
  [[ -f "$reg_file" ]] || return 0
  assert_registry_readable "$reg_file"
  names="$(node -e 'console.log(Object.keys(JSON.parse(require("node:fs").readFileSync(process.argv[1],"utf8"))).join("\n"))' "$reg_file" 2>/dev/null || true)"
  [[ -n "$names" ]] || return 0
  while IFS= read -r name; do
    [[ -n "$name" ]] || continue
    backup_sandbox "$name" >/dev/null || failures=$((failures + 1))
  done <<<"$names"
  [[ "$failures" -eq 0 ]] || { warn "${failures} sandbox backup(s) failed."; return 1; }
}

# recover_sandbox name — restarts an existing container, or recreates it from
# its most recent backup image if the container is gone but the registry
# entry remains.
recover_sandbox() {
  local name="$1" image port container_port port_spec latest_backup was_gateway_managed env_pairs
  if sandbox_exists "$name"; then
    sandbox_running "$name" || start_sandbox "$name"
    ok "Sandbox '${name}' recovered (container present)"
    return 0
  fi
  image="$(sandbox_registry_field "$name" image)"
  if [[ -z "$image" ]]; then
    warn "Sandbox '${name}' has no recorded image; cannot recover."
    return 1
  fi
  port="$(sandbox_registry_field "$name" port)"
  container_port="$(sandbox_registry_field "$name" containerPort)"
  was_gateway_managed="$(sandbox_registry_field "$name" gatewayManaged)"
  port_spec="${port}${container_port:+:${container_port}}"
  env_pairs="$(node -e '
    try {
      const r = JSON.parse(require("node:fs").readFileSync(process.argv[1], "utf8"));
      const env = r[process.argv[2]]?.env;
      if (Array.isArray(env)) process.stdout.write(env.join(" "));
    } catch {}
  ' "$(sandbox_registry_file)" "$name")"
  latest_backup="$(docker images --format '{{.Repository}}:{{.Tag}}' 2>/dev/null \
    | grep "^$(sandbox_container_name "$name")-backup-" | sort | tail -1 || true)"
  # Leave the existing registry entry in place until create_sandbox
  # succeeds and overwrites it -- sandbox_exists checks the container, not
  # the registry, so a stale entry here doesn't block recreation, and it's
  # the only metadata left to retry from if this attempt fails partway.
  # Recreate under the mode it was originally created with, regardless of
  # this session's current HARNESS_GATEWAY_ENABLED setting.
  HARNESS_GATEWAY_ENABLED="$([[ "$was_gateway_managed" == "true" ]] && printf 1 || printf '')" \
    create_sandbox "$name" "${latest_backup:-$image}" "$port_spec" "$env_pairs"
  if [[ -n "$latest_backup" ]]; then
    warn "Recovered sandbox '${name}' from backup image ${latest_backup}."
  fi
}

recover_all_sandboxes() {
  local reg_file names name failures=0
  reg_file="$(sandbox_registry_file)"
  [[ -f "$reg_file" ]] || return 0
  assert_registry_readable "$reg_file"
  names="$(node -e 'console.log(Object.keys(JSON.parse(require("node:fs").readFileSync(process.argv[1],"utf8"))).join("\n"))' "$reg_file" 2>/dev/null || true)"
  [[ -n "$names" ]] || return 0
  info "Recovering existing sandboxes…"
  while IFS= read -r name; do
    [[ -n "$name" ]] || continue
    recover_sandbox "$name" || failures=$((failures + 1))
  done <<<"$names"
  [[ "$failures" -eq 0 ]] || { warn "${failures} sandbox(es) could not be recovered."; return 1; }
}

# destroy_all_sandboxes — tears down every registered sandbox, used by the
# uninstaller. Best-effort: keeps going past individual failures.
destroy_all_sandboxes() {
  local reg_file names name failures=0
  reg_file="$(sandbox_registry_file)"
  [[ -f "$reg_file" ]] || return 0
  assert_registry_readable "$reg_file"
  names="$(node -e 'console.log(Object.keys(JSON.parse(require("node:fs").readFileSync(process.argv[1],"utf8"))).join("\n"))' "$reg_file" 2>/dev/null || true)"
  [[ -n "$names" ]] || return 0
  while IFS= read -r name; do
    [[ -n "$name" ]] || continue
    destroy_sandbox "$name" --force || failures=$((failures + 1))
  done <<<"$names"
  [[ "$failures" -eq 0 ]] || { warn "${failures} sandbox(es) could not be destroyed."; return 1; }
}
