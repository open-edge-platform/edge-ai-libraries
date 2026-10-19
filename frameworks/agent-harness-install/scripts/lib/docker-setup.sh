# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# shellcheck shell=bash
# Docker install + daemon/group readiness, with Intel GPU device passthrough.
# Intel GPUs need no CDI spec: render nodes under /dev/dri are passed
# straight through to containers via --device.

# Known-good SHA-256 for Docker's apt-repo signing key (identical bytes on
# both the ubuntu and debian download.docker.com endpoints as pinned here).
# Every docker-ce package apt installs afterwards is signature-verified
# against this key by apt itself — stronger than the one-shot convenience
# script below, which has no ongoing verification once it's run.
_DOCKER_APT_GPG_KEY_SHA256="1500c1f56fa9e26b9b8f42452a553675796ade0807cdce11975eb98170b3a570"

# install_docker_via_apt_repo distro_id — sets up Docker's official signed
# apt repository per docs.docker.com/engine/install/{ubuntu,debian}/, so
# Docker's package signature (not just this one download) backs every
# docker-ce install/upgrade from here on.
install_docker_via_apt_repo() {
  local distro_id="$1"
  info "Installing Docker via its official signed apt repository (sudo required)…"
  sudo apt-get update -qq
  sudo apt-get install -y -qq ca-certificates curl
  sudo install -m 0755 -d /etc/apt/keyrings

  local key_tmp
  key_tmp="$(mktemp)"
  fetch_and_verify "https://download.docker.com/linux/${distro_id}/gpg" "$key_tmp" \
    "Docker apt GPG key" "$_DOCKER_APT_GPG_KEY_SHA256"
  sudo install -m 0644 "$key_tmp" /etc/apt/keyrings/docker.asc
  rm -f "$key_tmp"

  local codename arch
  codename="$(. /etc/os-release && printf '%s' "${UBUNTU_CODENAME:-$VERSION_CODENAME}")"
  arch="$(dpkg --print-architecture)"
  sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/${distro_id}
Suites: ${codename}
Components: stable
Architectures: ${arch}
Signed-By: /etc/apt/keyrings/docker.asc
EOF

  sudo apt-get update -qq
  sudo apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin \
    || error "Docker install via the signed apt repository failed."
}

# install_docker_via_convenience_script — fallback for distros without a
# signed-repo path above (non-apt). No vendor-published static checksum
# exists for this rolling script; refuses to run it unverified by default
# (this runs as root via sudo) -- set DOCKER_INSTALL_SHA256 once you've
# reviewed a known-good copy, or DOCKER_ALLOW_UNVERIFIED_INSTALL=1 to accept
# the risk and proceed without pinning.
install_docker_via_convenience_script() {
  info "No signed apt repository available for this distro; falling back to
the official convenience script (sudo required)."
  if [[ -z "${DOCKER_INSTALL_SHA256:-}" && "${DOCKER_ALLOW_UNVERIFIED_INSTALL:-}" != "1" ]]; then
    error "DOCKER_INSTALL_SHA256 is not set, so refusing to run get.docker.com's
installer unverified as root. Download and review https://get.docker.com yourself,
then set DOCKER_INSTALL_SHA256=<sha256> to pin it (or DOCKER_ALLOW_UNVERIFIED_INSTALL=1
to accept the risk and proceed without pinning)."
  fi
  local docker_tmp
  docker_tmp="$(mktemp)"
  fetch_and_verify "https://get.docker.com" "$docker_tmp" "Docker install script" \
    "${DOCKER_INSTALL_SHA256:-}"
  assert_shell_script "$docker_tmp" "Docker install script"
  sudo sh "$docker_tmp" || { rm -f "$docker_tmp"; error "Docker install failed."; }
  rm -f "$docker_tmp"
}

# ensure_docker_daemon_proxy -- docker_proxy_env_args_into (openvino.sh,
# inference-router.sh) forwards HTTP_PROXY/
# HTTPS_PROXY/NO_PROXY into *containers* at runtime, but the Docker
# *daemon itself* needs the exact same proxy, as a separate systemd-level
# config, just to pull an image from Docker Hub in the first place -- no
# `docker run -e` flag can ever reach that. Without this, every pull of an
# image not already cached locally times out dialing registry-1.docker.io
# directly on any proxied corporate network, regardless of how correctly
# containers themselves end up configured. Keeps the daemon's config in
# sync either direction: a no-op if nothing changed, and removes a stale
# drop-in (not just skips adding one) if the proxy was unset since an
# earlier run -- otherwise the daemon would keep using an old proxy that
# may no longer exist/be reachable on a later, non-proxied network.
ensure_docker_daemon_proxy() {
  command_exists systemctl || return 0
  # systemctl exists on hosts without a running systemd (WSL1, containers);
  # nothing to configure there, and daemon-reload would fail.
  [[ -d /run/systemd/system ]] || return 0
  local http_proxy_val="${HTTP_PROXY:-${http_proxy:-}}"
  local https_proxy_val="${HTTPS_PROXY:-${https_proxy:-}}"
  local no_proxy_val="${NO_PROXY:-${no_proxy:-}}"
  local conf_dir="/etc/systemd/system/docker.service.d"
  local conf_file="${conf_dir}/http-proxy.conf"
  local marker="# Managed by agent-harness-install"

  if [[ -z "${http_proxy_val}${https_proxy_val}" ]]; then
    [[ -f "$conf_file" ]] || return 0
    # Only remove a drop-in this installer wrote, never someone else's.
    authorize_sudo || return 0
    _docker_proxy_dropin_is_ours "$conf_file" "$marker" || return 0
    info "No proxy set in this shell; removing the Docker daemon's previously configured proxy…"
    sudo rm -f "$conf_file"
    _restart_docker_daemon_for_proxy
    return 0
  fi

  # The values are written inside a double-quoted systemd Environment=
  # assignment, so a quote/backslash/newline would break out of it, and
  # systemd expands % specifiers there (a literal % must be written %%).
  local v
  for v in "$http_proxy_val" "$https_proxy_val" "$no_proxy_val"; do
    case "$v" in
      *'"'* | *'\'* | *$'\n'*)
        warn "Skipping Docker daemon proxy setup: a proxy variable contains a quote, backslash, or newline."
        return 0 ;;
    esac
  done
  http_proxy_val="${http_proxy_val//%/%%}"
  https_proxy_val="${https_proxy_val//%/%%}"
  no_proxy_val="${no_proxy_val//%/%%}"

  local tmp
  tmp="$(mktemp)"
  {
    echo "$marker"
    echo "[Service]"
    [[ -z "$http_proxy_val" ]] || printf 'Environment="HTTP_PROXY=%s"\n' "$http_proxy_val"
    [[ -z "$https_proxy_val" ]] || printf 'Environment="HTTPS_PROXY=%s"\n' "$https_proxy_val"
    [[ -z "$no_proxy_val" ]] || printf 'Environment="NO_PROXY=%s"\n' "$no_proxy_val"
  } >"$tmp"

  # The drop-in is root-only (0600, may embed proxy credentials), so even
  # the unchanged-check needs sudo to read it. Without sudo this is a
  # best-effort step: Docker may already be fine, so don't abort the install.
  if ! authorize_sudo; then
    rm -f "$tmp"
    warn "No sudo available; not configuring the Docker daemon's proxy. If image
pulls fail, configure it yourself (${conf_file})."
    return 0
  fi
  if sudo test -f "$conf_file"; then
    if ! _docker_proxy_dropin_is_ours "$conf_file" "$marker"; then
      rm -f "$tmp"
      warn "${conf_file} exists and was not created by this installer; leaving it as is."
      return 0
    fi
    if sudo cmp -s "$tmp" "$conf_file"; then
      rm -f "$tmp"
      return 0
    fi
  fi
  info "Configuring the Docker daemon's own proxy (for pulling images) from this shell's HTTP_PROXY/HTTPS_PROXY…"
  sudo mkdir -p "$conf_dir"
  sudo install -m 600 -o root -g root "$tmp" "$conf_file"
  rm -f "$tmp"
  _restart_docker_daemon_for_proxy
}

# _docker_proxy_dropin_is_ours FILE MARKER -- true only if FILE carries MARKER;
# an unmarked drop-in is never touched. Requires sudo (the file is root-only).
_docker_proxy_dropin_is_ours() {
  local file="$1" marker="$2"
  sudo grep -qxF "$marker" "$file" 2>/dev/null
}

# _restart_docker_daemon_for_proxy -- applies a changed proxy drop-in.
# Restarting dockerd stops running containers unless live-restore is on
# (--restart policies bring most back), so say so before doing it.
_restart_docker_daemon_for_proxy() {
  sudo systemctl daemon-reload
  if command_exists docker && [[ -n "$(docker ps -q 2>/dev/null)" ]]; then
    warn "Restarting the Docker daemon to apply the proxy change; running containers
will be restarted (those with a --restart policy come back automatically)."
  fi
  sudo systemctl restart docker 2>/dev/null || true
}

ensure_docker() {
  ensure_docker_daemon_proxy

  if docker info >/dev/null 2>&1; then
    return 0
  fi

  if ! command_exists docker; then
    info "Docker is not installed."
    local distro_id=""
    if command_exists apt-get && [[ -r /etc/os-release ]]; then
      distro_id="$(. /etc/os-release && printf '%s' "$ID")"
    fi
    case "$distro_id" in
      ubuntu | debian) install_docker_via_apt_repo "$distro_id" ;;
      *) install_docker_via_convenience_script ;;
    esac
  fi

  if command_exists systemctl && ! systemctl is-active --quiet docker 2>/dev/null; then
    info "Starting the Docker daemon."
    sudo systemctl enable --now docker 2>/dev/null || true
  fi

  if [[ "$(id -u)" -eq 0 ]]; then
    docker info >/dev/null 2>&1 || error "Docker is installed but not reachable."
    return 0
  fi

  local current_user
  current_user="$(id -un)"
  if ! id -nG "$current_user" 2>/dev/null | tr ' ' '\n' | grep -qx docker; then
    info "Adding '$current_user' to the docker group (sudo required)."
    warn "Docker group membership grants root-equivalent control of this host —
grant it only on trusted single-user machines."
    sudo usermod -aG docker "$current_user"
  fi

  docker info >/dev/null 2>&1 && return 0
  # Not reachable yet -- could be stale group credentials in *this* process
  # (just added above, or added by something else before this run started)
  # or a genuine problem. ensure_docker_group_active() (called right after
  # this by every top-level entry point) tells those apart and self-heals
  # the former by re-exec'ing under the new group; a real problem still
  # surfaces as this same error on that retry.
  return 2
}

# ensure_docker_group_active script_path [args...] -- call right after
# ensure_docker from every top-level entry point (startup.sh, scripts/
# install.sh), passing that *script's own* $0 and original "$@". If Docker
# still isn't reachable specifically because this process's group
# credentials predate a docker-group membership the system already granted
# (just now, or earlier), restarts script_path under the new group so it's
# active immediately -- no new terminal/login session needed. A genuine
# Docker problem (daemon down, not installed, etc.) is left alone; the
# caller's own post-call `docker info` check still reports it. Guarded by
# HARNESS_DOCKER_GROUP_REEXEC_DONE against re-exec looping if that turns
# out to be the real cause instead.
ensure_docker_group_active() {
  [[ -z "${SKIP_DOCKER:-}" ]] || return 0
  local script_path="$1"
  shift
  local docker_err
  docker_err="$(docker info 2>&1 >/dev/null)" && return 0
  # Only a permission error means stale group credentials; a stopped daemon
  # or a missing binary won't be fixed by re-running under the group.
  [[ "$docker_err" == *"permission denied"* ]] || return 0
  id -nG "$(id -un)" 2>/dev/null | tr ' ' '\n' | grep -qx docker || return 0
  [[ "${HARNESS_DOCKER_GROUP_REEXEC_DONE:-}" != "1" ]] || return 0

  info "Docker group membership was just granted -- restarting under the new group
instead of requiring a new terminal…"
  if command_exists sg; then
    HARNESS_DOCKER_GROUP_REEXEC_DONE=1 exec sg docker -c "$(printf '%q ' bash "$script_path" "$@")"
  fi
  # sg isn't guaranteed to be installed (confirmed missing on a real Ubuntu
  # test host, despite usermod/sudo -- same shadow-utils family -- being
  # present) -- sudo -u <self> re-initializes this user's full
  # supplementary-group list from /etc/group (via PAM/initgroups), the
  # same refresh a brand new login session would do, without sg/newgrp. -E
  # is needed since sudo resets the environment by default; this installer
  # already requires unrestricted sudo throughout (apt-get, usermod), so a
  # policy blocking -E specifically would be unusual.
  if command_exists sudo; then
    # sudo's secure_path would otherwise replace PATH, losing nvm/~/.local/bin
    # entries; re-pass it explicitly through env.
    HARNESS_DOCKER_GROUP_REEXEC_DONE=1 exec sudo -E -u "$(id -un)" -- env "PATH=$PATH" bash "$script_path" "$@"
  fi

  warn "Docker group membership was just granted but isn't active in this shell,
and neither 'sg' nor 'sudo' are available here to refresh it automatically."
  warn "Run: newgrp docker   (or log out and back in), then re-run this installer."
  exit 2
}

# Prints the --device args for Intel-vendor render nodes only (never card
# nodes -- containers only need render access, and passing card nodes would
# grant more than the documented workload requires). Cross-references
# /sys/class/drm's PCI vendor to avoid handing a container another GPU
# vendor's render node.
intel_gpu_docker_device_args() {
  local drm_dir vendor render_num node
  for drm_dir in /sys/class/drm/renderD*; do
    [[ -e "${drm_dir}/device/vendor" ]] || continue
    vendor="$(cat "${drm_dir}/device/vendor" 2>/dev/null || true)"
    [[ "$vendor" == "0x${INTEL_PCI_VENDOR_ID}" ]] || continue
    render_num="${drm_dir##*/renderD}"
    node="/dev/dri/renderD${render_num}"
    [[ -e "$node" ]] || continue
    printf ' --device=%s' "$node"
  done
}

# Prints --group-add=<gid> for each Intel render node's owning group
# (deduplicated), to pair with intel_gpu_docker_device_args's --device args.
# --device alone only grants the container the device *node*; the kernel
# still enforces that node's own owner/group permission bits (typically
# root:render, mode 660) against whatever uid/gid the container process
# actually runs as. OVMS's own docs (accelerators.md, "Using AI
# Accelerators") document --group-add=$(stat -c '%g' /dev/dri/render* | head
# -n 1) as a required *additional* flag alongside --device for GPU-targeted
# containers -- without it, a container running as the image's own fixed
# user (e.g. the published openvino/model_server image's uid 5000 'ovms'
# user, which has no reason to share the host's render GID) gets a
# permission-denied opening the render node even though --device correctly
# attached it.
intel_gpu_docker_group_add_args() {
  local drm_dir vendor render_num node gid seen=" "
  for drm_dir in /sys/class/drm/renderD*; do
    [[ -e "${drm_dir}/device/vendor" ]] || continue
    vendor="$(cat "${drm_dir}/device/vendor" 2>/dev/null || true)"
    [[ "$vendor" == "0x${INTEL_PCI_VENDOR_ID}" ]] || continue
    render_num="${drm_dir##*/renderD}"
    node="/dev/dri/renderD${render_num}"
    [[ -e "$node" ]] || continue
    gid="$(stat -c '%g' "$node" 2>/dev/null || true)"
    [[ -n "$gid" ]] || continue
    case "$seen" in *" ${gid} "*) continue ;; esac
    seen="${seen}${gid} "
    printf ' --group-add=%s' "$gid"
  done
}

# docker_proxy_env_args_into arr_name — appends -e KEY=VALUE docker args for
# any set proxy env var to the named array (nameref). Docker does not forward
# the host's proxy environment into containers automatically, so without this
# an OVMS/Inference Router container behind a corporate proxy can't reach the
# network even though the host process that started it can.
docker_proxy_env_args_into() {
  local -n _docker_proxy_target="$1"
  local var
  for var in HTTP_PROXY HTTPS_PROXY ALL_PROXY NO_PROXY http_proxy https_proxy all_proxy no_proxy; do
    [[ -n "${!var:-}" ]] && _docker_proxy_target+=(-e "${var}=${!var}")
  done
}
