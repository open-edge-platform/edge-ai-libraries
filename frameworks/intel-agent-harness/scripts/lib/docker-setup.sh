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
# exists for this rolling script; set DOCKER_INSTALL_SHA256 to pin it once
# you've reviewed a known-good copy, otherwise it's verified for shape only.
install_docker_via_convenience_script() {
  info "No signed apt repository available for this distro; falling back to
the official convenience script (sudo required)."
  local docker_tmp
  docker_tmp="$(mktemp)"
  fetch_and_verify "https://get.docker.com" "$docker_tmp" "Docker install script" \
    "${DOCKER_INSTALL_SHA256:-}"
  assert_shell_script "$docker_tmp" "Docker install script"
  sudo sh "$docker_tmp" || { rm -f "$docker_tmp"; error "Docker install failed."; }
  rm -f "$docker_tmp"
}

ensure_docker() {
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
    warn "Docker group membership is not active in this shell yet."
    warn "Run: newgrp docker   (or log out and back in), then re-run this installer."
    exit 0
  fi

  docker info >/dev/null 2>&1 || error "Docker is installed but not reachable. Try: sudo systemctl start docker"
}

# Prints the --device args needed to pass Intel GPU render nodes into a container.
intel_gpu_docker_device_args() {
  local node
  for node in /dev/dri/renderD* /dev/dri/card*; do
    [[ -e "$node" ]] && printf ' --device=%s' "$node"
  done
}

# docker_proxy_env_args_into arr_name — appends -e KEY=VALUE docker args for
# any set proxy env var to the named array (nameref). Docker does not forward
# the host's proxy environment into containers automatically, so without this
# an OVMS/sandbox/gateway container behind a corporate proxy can't reach the
# network even though the host process that started it can.
docker_proxy_env_args_into() {
  local -n _docker_proxy_target="$1"
  local var
  for var in HTTP_PROXY HTTPS_PROXY ALL_PROXY NO_PROXY http_proxy https_proxy all_proxy no_proxy; do
    [[ -n "${!var:-}" ]] && _docker_proxy_target+=(-e "${var}=${!var}")
  done
}
