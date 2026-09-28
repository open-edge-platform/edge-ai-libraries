# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# shellcheck shell=bash
# Optional sandbox gateway — a single shared reverse-proxy container that
# mediates traffic to sandboxes instead of each one publishing its own host
# port. Off by default (HARNESS_GATEWAY_ENABLED=1 turns it on) so existing
# direct-port sandboxes keep working unchanged.
#
# Routes (name -> internal target URL + optional server-held credential) are
# recorded in a JSON file under the state directory; the proxy re-reads it on
# every request, so no gateway restart is needed to add/remove a route. A
# client's own Authorization header is never forwarded to the target — only
# the credential the route was registered with, if any.

HARNESS_GATEWAY_ENABLED="${HARNESS_GATEWAY_ENABLED:-}"
HARNESS_GATEWAY_NETWORK="${HARNESS_GATEWAY_NETWORK:-intel-agent-net}"
HARNESS_GATEWAY_CONTAINER="${HARNESS_GATEWAY_CONTAINER:-intel-agent-gateway}"
HARNESS_GATEWAY_IMAGE="${HARNESS_GATEWAY_IMAGE:-node:22-alpine}"
HARNESS_GATEWAY_PORT="${HARNESS_GATEWAY_PORT:-8888}"

sandbox_gateway_enabled() {
  [[ "$HARNESS_GATEWAY_ENABLED" == "1" ]]
}

gateway_state_dir() {
  local root
  root="$(ensure_state_dir)"
  (umask 077 && mkdir -p "${root}/gateway")
  printf '%s/gateway' "$root"
}

gateway_routes_file() {
  printf '%s/routes.json' "$(gateway_state_dir)"
}

# Regenerated on every gateway start so a container recreated from an older
# image always runs this install's current proxy logic.
ensure_gateway_proxy_script() {
  local script_path
  script_path="$(gateway_state_dir)/proxy.mjs"
  cat >"$script_path" <<'NODE'
import http from "node:http";
import fs from "node:fs";

const ROUTES_FILE = process.env.GATEWAY_ROUTES_FILE || "/gateway/routes.json";
const PORT = Number(process.env.GATEWAY_PORT || 8888);

function loadRoutes() {
  try {
    return JSON.parse(fs.readFileSync(ROUTES_FILE, "utf8"));
  } catch {
    return {};
  }
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url, "http://gateway");
  const segments = url.pathname.split("/").filter(Boolean);
  const routeName = segments.shift();
  const route = routeName ? loadRoutes()[routeName] : undefined;
  if (!route || !route.target) {
    res.writeHead(502, { "content-type": "text/plain" });
    res.end(`No route registered for '${routeName || ""}'\n`);
    return;
  }
  let target;
  try {
    target = new URL(route.target);
  } catch {
    res.writeHead(502, { "content-type": "text/plain" });
    res.end(`Route '${routeName}' has an invalid target\n`);
    return;
  }
  const forwardPath = "/" + segments.join("/") + url.search;
  const headers = { ...req.headers, host: target.host };
  // Never trust a client-supplied credential — only the one this route was
  // registered with (if any) is ever sent to the real target.
  delete headers.authorization;
  if (route.authHeader) headers.authorization = route.authHeader;
  const proxyReq = http.request(
    {
      hostname: target.hostname,
      port: target.port || 80,
      path: forwardPath,
      method: req.method,
      headers,
    },
    (proxyRes) => {
      res.writeHead(proxyRes.statusCode || 502, proxyRes.headers);
      proxyRes.pipe(res);
    },
  );
  proxyReq.on("error", (err) => {
    res.writeHead(502, { "content-type": "text/plain" });
    res.end(`Gateway could not reach route '${routeName}': ${err.message}\n`);
  });
  req.pipe(proxyReq);
});

server.listen(PORT, () => console.log(`Harness gateway listening on :${PORT}`));
NODE
  chmod 600 "$script_path"
}

ensure_gateway_network() {
  docker network inspect "$HARNESS_GATEWAY_NETWORK" >/dev/null 2>&1 \
    || docker network create "$HARNESS_GATEWAY_NETWORK" >/dev/null \
    || error "Could not create gateway network '${HARNESS_GATEWAY_NETWORK}'."
}

ensure_gateway_running() {
  local routes_file
  local -a proxy_args=()
  if [[ ! "$HARNESS_GATEWAY_PORT" =~ ^[0-9]+$ ]] || ! ((HARNESS_GATEWAY_PORT >= 1024 && HARNESS_GATEWAY_PORT <= 65535)); then
    error "HARNESS_GATEWAY_PORT must be an integer between 1024 and 65535."
  fi
  ensure_gateway_network
  ensure_gateway_proxy_script
  routes_file="$(gateway_routes_file)"
  [[ -f "$routes_file" ]] || printf '{}' >"$routes_file"
  if docker inspect "$HARNESS_GATEWAY_CONTAINER" >/dev/null 2>&1; then
    docker start "$HARNESS_GATEWAY_CONTAINER" >/dev/null 2>&1 || true
    return 0
  fi
  docker_proxy_env_args_into proxy_args
  info "Starting harness gateway on port ${HARNESS_GATEWAY_PORT}…"
  docker run -d --name "$HARNESS_GATEWAY_CONTAINER" --restart unless-stopped \
    --network "$HARNESS_GATEWAY_NETWORK" \
    -p "${HARNESS_GATEWAY_PORT}:${HARNESS_GATEWAY_PORT}" \
    -v "$(gateway_state_dir):/gateway:ro" \
    -e "GATEWAY_PORT=${HARNESS_GATEWAY_PORT}" -e "GATEWAY_ROUTES_FILE=/gateway/routes.json" \
    "${proxy_args[@]}" \
    "$HARNESS_GATEWAY_IMAGE" node /gateway/proxy.mjs \
    || error "Could not start the harness gateway."
  ok "Harness gateway is running on port ${HARNESS_GATEWAY_PORT}"
}

# gateway_set_route name target [auth_header] — registers/updates a route.
# Read per-request by the proxy, so no gateway restart is needed.
gateway_set_route() {
  local name="$1" target="$2" auth_header="${3:-}"
  with_state_lock gateway-routes _gateway_set_route_locked "$name" "$target" "$auth_header"
}

_gateway_set_route_locked() {
  local name="$1" target="$2" auth_header="$3" routes_file tmp
  routes_file="$(gateway_routes_file)"
  assert_state_path_safe "$routes_file"
  tmp="$(mktemp)"
  node -e '
    const fs = require("node:fs");
    const [routesFile, name, target, authHeader] = process.argv.slice(1);
    let routes = {};
    try { routes = JSON.parse(fs.readFileSync(routesFile, "utf8")); } catch {}
    routes[name] = authHeader ? { target, authHeader } : { target };
    process.stdout.write(JSON.stringify(routes, null, 2));
  ' "$routes_file" "$name" "$target" "$auth_header" >"$tmp" \
    || { rm -f "$tmp"; error "Could not update gateway routes."; }
  chmod 600 "$tmp"
  mv -f "$tmp" "$routes_file"
  assert_state_path_safe "$routes_file"
  assert_owned_by_current_user "$routes_file"
}

gateway_remove_route() {
  local name="$1"
  # Existence check only — must not create the gateway state dir as a side
  # effect, since this runs on every sandbox destroy whether or not the
  # gateway feature is actually in use.
  [[ -f "$(platform_state_root)/gateway/routes.json" ]] || return 0
  with_state_lock gateway-routes _gateway_remove_route_locked "$name"
}

_gateway_remove_route_locked() {
  local name="$1" routes_file tmp
  routes_file="$(gateway_routes_file)"
  [[ -f "$routes_file" ]] || return 0
  assert_state_path_safe "$routes_file"
  tmp="$(mktemp)"
  node -e '
    const fs = require("node:fs");
    const [routesFile, name] = process.argv.slice(1);
    let routes = {};
    try { routes = JSON.parse(fs.readFileSync(routesFile, "utf8")); } catch {}
    delete routes[name];
    process.stdout.write(JSON.stringify(routes, null, 2));
  ' "$routes_file" "$name" >"$tmp"
  chmod 600 "$tmp"
  mv -f "$tmp" "$routes_file"
  assert_state_path_safe "$routes_file"
  assert_owned_by_current_user "$routes_file"
}

gateway_route_url() {
  printf 'http://%s:%s/%s' "$(resolve_advertised_host)" "$HARNESS_GATEWAY_PORT" "$1"
}

# Used by the uninstaller; best-effort, leaves the image untouched.
remove_gateway() {
  command_exists docker || return 0
  docker rm -f "$HARNESS_GATEWAY_CONTAINER" >/dev/null 2>&1 || true
  docker network rm "$HARNESS_GATEWAY_NETWORK" >/dev/null 2>&1 || true
}
