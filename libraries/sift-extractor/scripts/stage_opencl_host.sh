#!/usr/bin/env bash

set -euo pipefail

usage() {
  printf 'Usage: %s <user@host> [OpenCL-include-root]\n' "$0" >&2
}

if [[ $# -lt 1 || $# -gt 2 ]]; then
  usage
  exit 2
fi

remote="$1"
opencl_include_root="${2:-${OPENCL_INCLUDE_ROOT:-/opt/intel/oneapi/compiler/latest/include}}"
component_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

for header in cl.h cl_ext.h cl_platform.h cl_version.h; do
  if [[ ! -r "$opencl_include_root/CL/$header" ]]; then
    printf 'Missing OpenCL header: %s\n' "$opencl_include_root/CL/$header" >&2
    exit 1
  fi
done

stage_root="$(mktemp -d)"
trap 'rm -rf "$stage_root"' EXIT
mkdir -p "$stage_root/libraries/sift-extractor" "$stage_root/CL"
cp -a "$component_dir/." "$stage_root/libraries/sift-extractor/"
cp "$opencl_include_root/CL/cl.h" \
   "$opencl_include_root/CL/cl_ext.h" \
   "$opencl_include_root/CL/cl_platform.h" \
   "$opencl_include_root/CL/cl_version.h" \
   "$stage_root/CL/"

(
  cd "$stage_root"
  find libraries/sift-extractor CL -type f -print0 |
    sort -z |
    xargs -0 sha256sum > SHA256SUMS
)
stage_id="$(sha256sum "$stage_root/SHA256SUMS" | cut -c1-16)"

remote_command="set -eu; parent=\"\$HOME/.local/share/sift-extractor-staging\"; dest=\"\$parent/$stage_id\"; mkdir -p \"\$parent\"; if test -e \"\$dest\"; then printf 'Refusing to overwrite existing stage: %s\\n' \"\$dest\" >&2; exit 1; fi; mkdir \"\$dest\"; tar -xzf - -C \"\$dest\"; cd \"\$dest\"; sha256sum -c SHA256SUMS"
tar -czf - -C "$stage_root" . | ssh -o StrictHostKeyChecking=yes "$remote" "$remote_command"

printf 'Verified stage: %s:%s/%s\n' "$remote" \
  '$HOME/.local/share/sift-extractor-staging' "$stage_id"
