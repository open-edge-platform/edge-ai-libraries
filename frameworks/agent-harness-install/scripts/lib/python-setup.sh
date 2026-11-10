# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# shellcheck shell=bash
# Python prerequisites — python3 + a working venv module + PyYAML, needed by
# the hf-snapshot/export-model-py OVMS exporters (scripts/lib/openvino.sh)
# and by test/full-flow-test.sh's own config.yaml-parsing checks. Previously
# left entirely to the operator to install by hand (see
# docs/user-guide/known-limitations.md); ./startup.sh now automates it.

# python_venv_usable -- true if python3 can actually create a venv.
# Debian/Ubuntu ship python3-venv as a separate package from base python3;
# `python3 -m venv --help` succeeds without it, but creating a venv fails
# partway through on the missing ensurepip bootstrap, so probe a real one.
python_venv_usable() {
  local probe rc=0
  command_exists python3 || return 1
  probe="$(mktemp -d)" || return 1
  python3 -m venv "${probe}/venv" >/dev/null 2>&1 || rc=1
  rm -rf -- "$probe"
  return "$rc"
}

python_yaml_usable() {
  command_exists python3 && python3 -c 'import yaml' >/dev/null 2>&1
}

# ensure_python_prereqs -- installs python3/python3-venv/PyYAML via apt when
# missing (Debian/Ubuntu only, matching this installer's other apt-based
# bootstraps); errors with manual-install guidance on other distros.
ensure_python_prereqs() {
  if ! command_exists python3 || ! python_venv_usable; then
    info "python3/venv not ready; installing…"
    if command_exists apt-get; then
      require_sudo_or_fail "installing python3/python3-venv"
      sudo apt-get update -qq
      sudo apt-get install -y -qq python3 python3-venv python3-pip
    else
      error "python3 (with a working venv module) is required but this installer
only knows how to install it via apt-get. Install python3, python3-venv, and
python3-pip yourself, then re-run."
    fi
    python_venv_usable || error "python3-venv install did not take effect (creating a test venv still fails)."
  fi
  ok "Python 3 + venv ready ($(python3 --version 2>&1))"

  if ! python_yaml_usable; then
    info "PyYAML not found for python3; installing…"
    if command_exists apt-get; then
      require_sudo_or_fail "installing python3-yaml"
      sudo apt-get update -qq
      sudo apt-get install -y -qq python3-yaml
    elif command_exists pip3; then
      pip3 install --user --quiet pyyaml
    else
      error "PyYAML is required but neither apt-get nor pip3 is available to install
it. Install it yourself (pip install pyyaml), then re-run."
    fi
    python_yaml_usable || error "PyYAML install did not take effect (python3 -c 'import yaml' still fails)."
  fi
  ok "PyYAML available for python3"
}
