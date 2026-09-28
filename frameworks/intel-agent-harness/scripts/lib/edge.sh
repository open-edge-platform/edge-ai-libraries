# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# shellcheck shell=bash
# Generic Dockerized edge-microservice manager. Clones/builds (or uses a
# prebuilt image), stands the result up as a sandbox via sandbox.sh, and
# reports the endpoint so it can be registered with a Harness agent
# (harness-mcp.sh). Not specific to any one project.
#
# Configure via env vars:
#   EDGE_SERVICE_REPO_URL       git remote containing the service's Dockerfile
#   EDGE_SERVICE_REF            git ref/tag to build from (default: main)
#   EDGE_SERVICE_DOCKERFILE     path to the Dockerfile within the repo
#   EDGE_SERVICE_BUILD_CONTEXT  build context within the repo (default: repo root)
#   EDGE_SERVICE_IMAGE          prebuilt image to use instead of cloning/building
#   EDGE_SERVICE_ENV            space-separated KEY=VALUE pairs passed to the container
#   EDGE_SERVICE_CONTAINER_PORT fixed internal port the image listens on, if not configurable
#   EDGE_SERVICE_MCP_PATH       MCP endpoint path for the printed URL (default: /mcp)

edge_service_source_dir() {
  printf '%s/edge-services/%s/source' "$(harness_state_root)" "$1"
}

resolve_edge_service_source() {
  local name="$1" src_dir ref
  [[ -n "${EDGE_SERVICE_REPO_URL:-}" ]] || error "Set EDGE_SERVICE_REPO_URL (git repo
containing ${name}'s Dockerfile) to build an edge service from source, or set
EDGE_SERVICE_IMAGE to use a prebuilt image instead."
  ensure_state_dir >/dev/null
  src_dir="$(edge_service_source_dir "$name")"
  assert_state_path_safe "$src_dir"
  ref="${EDGE_SERVICE_REF:-main}"
  rm -rf "$src_dir"
  mkdir -p "$(dirname "$src_dir")"
  info "Cloning ${name} source from ${EDGE_SERVICE_REPO_URL}@${ref}…"
  clone_git_ref "$EDGE_SERVICE_REPO_URL" "$ref" "$src_dir"
  printf '%s' "$src_dir"
}

build_edge_service_image() {
  local name="$1" src_dir dockerfile context tag
  [[ -n "${EDGE_SERVICE_DOCKERFILE:-}" ]] || error "Set EDGE_SERVICE_DOCKERFILE to the
Dockerfile path (relative to the repo root) that builds ${name}."
  src_dir="$(resolve_edge_service_source "$name")"
  dockerfile="${src_dir}/${EDGE_SERVICE_DOCKERFILE}"
  [[ -f "$dockerfile" ]] || error "Dockerfile not found: ${dockerfile}"
  context="${src_dir}"
  [[ -z "${EDGE_SERVICE_BUILD_CONTEXT:-}" ]] || context="${src_dir}/${EDGE_SERVICE_BUILD_CONTEXT}"
  tag="${name}:local"
  spin "Building ${name} image (${tag})" docker build -f "$dockerfile" -t "$tag" "$context"
  printf '%s' "$tag"
}

resolve_edge_service_image() {
  local name="$1"
  if [[ -n "${EDGE_SERVICE_IMAGE:-}" ]]; then
    printf '%s' "$EDGE_SERVICE_IMAGE"
  else
    build_edge_service_image "$name"
  fi
}

edge_service_endpoint() {
  local name="$1" port path gateway_managed
  path="${EDGE_SERVICE_MCP_PATH:-/mcp}"
  gateway_managed="$(sandbox_registry_field "$name" gatewayManaged)"
  if [[ "$gateway_managed" == "true" ]]; then
    printf '%s%s' "$(gateway_route_url "$name")" "$path"
    return 0
  fi
  port="$(sandbox_registry_field "$name" port)"
  [[ -n "$port" ]] || error "No registered port for edge service '${name}'; is it running?"
  printf 'http://%s:%s%s' "$(resolve_advertised_host)" "$port" "$path"
}

create_edge_service() {
  local name="$1" image port_spec=""
  [[ -n "$name" ]] || error "edge create requires a service name."
  validate_sandbox_name "$name" || error "Edge service name '$name' must be lowercase
letters/digits/hyphens, start/end alphanumeric, no consecutive hyphens."
  image="$(resolve_edge_service_image "$name")"
  if [[ -n "${EDGE_SERVICE_CONTAINER_PORT:-}" ]]; then
    if sandbox_gateway_enabled; then
      # Gateway mode never publishes a host port, so there's no host-side
      # availability to check -- just pass the logical container port.
      port_spec="$EDGE_SERVICE_CONTAINER_PORT"
    else
      port_spec="$(resolve_available_gateway_port):${EDGE_SERVICE_CONTAINER_PORT}"
    fi
  fi
  create_sandbox "$name" "$image" "$port_spec" "${EDGE_SERVICE_ENV:-}"
  ok "Edge service '${name}' endpoint: $(edge_service_endpoint "$name")"
}

destroy_edge_service() {
  local name="$1"
  [[ -n "$name" ]] || error "edge destroy requires a service name."
  destroy_sandbox "$name" --force
}
