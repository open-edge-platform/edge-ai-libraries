#!/usr/bin/env bash

set -u

section() {
  printf '\n=== %s ===\n' "$1"
}

section "Host"
uname -a
if [[ -r /etc/os-release ]]; then
  . /etc/os-release
  printf 'OS: %s %s\n' "${PRETTY_NAME:-unknown}" "${VERSION_ID:-}"
fi

section "CPU"
if command -v lscpu >/dev/null 2>&1; then
  lscpu | grep -E '^(Architecture|Model name|CPU\(s\)|Thread\(s\) per core|Core\(s\) per socket|Socket\(s\)|CPU max MHz|NUMA node\(s\)|L[123]):' || true
else
  printf 'lscpu: unavailable\n'
fi

section "Memory"
if command -v free >/dev/null 2>&1; then
  free -h
else
  printf 'free: unavailable\n'
fi

section "Display and compute devices"
if command -v lspci >/dev/null 2>&1; then
  lspci -nn | grep -Ei 'vga|3d|display|processing accelerator' || true
else
  printf 'lspci: unavailable\n'
fi
for device_path in /dev/dri/renderD*; do
  if [[ -e "$device_path" ]]; then
    printf 'DRI device: %s\n' "$device_path"
  fi
done
for driver in i915 xe; do
  if [[ -r "/sys/module/$driver/version" ]]; then
    printf '%s driver: ' "$driver"
    cat "/sys/module/$driver/version"
  fi
done

section "OpenCL ICDs"
if [[ -d /etc/OpenCL/vendors ]]; then
  find /etc/OpenCL/vendors -maxdepth 1 -type f -print -exec sed -n '1p' {} \;
else
  printf '/etc/OpenCL/vendors: unavailable\n'
fi

section "oneAPI installations"
found_oneapi=0
for oneapi_path in /opt/intel/oneapi/*; do
  if [[ -d "$oneapi_path" ]]; then
    printf '%s\n' "$oneapi_path"
    found_oneapi=1
  fi
done
if [[ "$found_oneapi" -eq 0 ]]; then
  printf '/opt/intel/oneapi: unavailable\n'
fi

find_tool() {
  local tool_name="$1"
  local candidate
  if command -v "$tool_name" >/dev/null 2>&1; then
    command -v "$tool_name"
    return
  fi
  case "$tool_name" in
    icpx)
      for candidate in /opt/intel/oneapi/compiler/*/bin/icpx; do
        if [[ -x "$candidate" ]]; then
          printf '%s\n' "$candidate"
          return
        fi
      done
      ;;
    sycl-ls)
      for candidate in /opt/intel/oneapi/compiler/*/bin/sycl-ls; do
        if [[ -x "$candidate" ]]; then
          printf '%s\n' "$candidate"
          return
        fi
      done
      ;;
  esac
}

section "Toolchains and runtimes"
for tool_name in cmake ctest icpx sycl-ls clinfo; do
  tool_path="$(find_tool "$tool_name")"
  if [[ -z "$tool_path" ]]; then
    printf '%s: unavailable\n' "$tool_name"
    continue
  fi
  printf '%s: %s\n' "$tool_name" "$tool_path"
  case "$tool_name" in
    icpx)
      "$tool_path" --version 2>&1 | head -n 3 || true
      ;;
    sycl-ls)
      "$tool_path" 2>&1 || true
      ;;
    clinfo)
      "$tool_path" -l 2>&1 || true
      ;;
  esac
done
