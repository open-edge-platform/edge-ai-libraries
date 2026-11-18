#!/usr/bin/env bash

set -euo pipefail

usage() {
  printf 'Usage: %s <user@host> [OpenCL-include-root] [--test]\n' "$0" >&2
}

if [[ $# -lt 1 || $# -gt 3 ]]; then
  usage
  exit 2
fi

remote="$1"
shift
opencl_include_root="${OPENCL_INCLUDE_ROOT:-/opt/intel/oneapi/compiler/latest/include}"
run_tests=0
include_was_set=0
for argument in "$@"; do
  if [[ "$argument" == --test ]]; then
    run_tests=1
  elif [[ "$include_was_set" -eq 0 && "$argument" != -* ]]; then
    opencl_include_root="$argument"
    include_was_set=1
  else
    usage
    exit 2
  fi
done
if [[ "$remote" == -* || "$remote" == *[[:space:]]* ]]; then
  printf 'Invalid SSH destination\n' >&2
  exit 2
fi
component_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -n "${SIFT_STAGE_PAIR_IMAGE:-}" && -z "${SIFT_STAGE_SYCL_BUILD:-}" ]]; then
  printf 'SIFT_STAGE_PAIR_IMAGE requires SIFT_STAGE_SYCL_BUILD\n' >&2
  exit 2
fi

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

if [[ -n "${SIFT_STAGE_SYCL_BUILD:-}" ]]; then
  compiler_root="$(cd "$opencl_include_root/.." && pwd -P)"
  level_zero_loader="${SIFT_STAGE_LEVEL_ZERO_LOADER:-$(ldconfig -p | awk '$1 == "libze_loader.so.1" && /x86-64/ && !found {print $NF; found=1}')}"
  level_zero_tracing="${SIFT_STAGE_LEVEL_ZERO_TRACING:-$(dirname "$level_zero_loader")/libze_tracing_layer.so.1}"
  level_zero_notice="${SIFT_STAGE_LEVEL_ZERO_NOTICE:-/usr/share/doc/libze1/copyright}"
  if [[ ! -r "$level_zero_loader" || ! -r "$level_zero_tracing" || ! -r "$level_zero_notice" ]]; then
    printf 'Missing Level Zero loader, matching tracing layer or notices; set SIFT_STAGE_LEVEL_ZERO_LOADER, SIFT_STAGE_LEVEL_ZERO_TRACING and SIFT_STAGE_LEVEL_ZERO_NOTICE\n' >&2
    exit 1
  fi
  if ! nm -D --defined-only "$level_zero_loader" | awk '$3 == "zeDeviceGetRootDevice" {found=1} END {exit !found}'; then
    printf 'Level Zero loader must export zeDeviceGetRootDevice: %s\n' "$level_zero_loader" >&2
    exit 1
  fi
  runtime_seeds=(
    "$compiler_root/lib/libsycl.so.8"
    "$compiler_root/lib/libur_loader.so.0"
    "$compiler_root/lib/libur_adapter_level_zero.so.0"
    "$compiler_root/lib/libur_adapter_opencl.so.0"
  )
  mkdir -p "$stage_root/sycl-runtime/lib" "$stage_root/sycl-runtime/bin" \
    "$stage_root/sycl-runtime/notices"
  for test_name in test_sift_sycl_kernels test_sift_sycl_extract test_sift_sycl_match; do
    cp "$SIFT_STAGE_SYCL_BUILD/$test_name" "$stage_root/sycl-runtime/bin/"
  done
  runtime_executables=("$SIFT_STAGE_SYCL_BUILD/test_sift_sycl_extract")
  if [[ -n "${SIFT_STAGE_PAIR_IMAGE:-}" ]]; then
    if [[ ! -r "$SIFT_STAGE_PAIR_IMAGE" || -z "${SIFT_STAGE_OPENCV_PREFIX:-}" ||
          ! -d "$SIFT_STAGE_OPENCV_PREFIX/share/licenses/opencv4" ]]; then
      printf 'Comparison requires a readable fixture and SIFT_STAGE_OPENCV_PREFIX with license notices\n' >&2
      exit 1
    fi
    cp "$SIFT_STAGE_SYCL_BUILD/validate_sift_pair" "$stage_root/sycl-runtime/bin/"
    cp "$SIFT_STAGE_PAIR_IMAGE" "$stage_root/comparison-input.pgm"
    cp -a "$SIFT_STAGE_OPENCV_PREFIX/share/licenses/opencv4" \
      "$stage_root/sycl-runtime/notices/opencv"
    runtime_executables+=("$SIFT_STAGE_SYCL_BUILD/validate_sift_pair")
  fi
  ldd "${runtime_seeds[@]}" "$level_zero_loader" "$level_zero_tracing" "${runtime_executables[@]}" \
    > "$stage_root/sycl-runtime/linked-libraries.txt"
  if grep -q 'not found' "$stage_root/sycl-runtime/linked-libraries.txt"; then
    printf 'Unresolved local runtime dependencies; source oneAPI setvars first\n' >&2
    exit 1
  fi
  for library in "${runtime_seeds[@]}"; do
    cp -L "$library" "$stage_root/sycl-runtime/lib/"
  done
  cp -L "$level_zero_loader" "$stage_root/sycl-runtime/lib/libze_loader.so.1"
  cp -L "$level_zero_tracing" "$stage_root/sycl-runtime/lib/libze_tracing_layer.so.1"
  cp -a "$level_zero_notice" "$stage_root/sycl-runtime/notices/level-zero"
  while IFS= read -r library; do
    cp -L "$library" "$stage_root/sycl-runtime/lib/"
  done < <(awk '$2 == "=>" && $3 ~ /^\/opt\/intel\/oneapi\// && $3 !~ /libOpenCL/ {print $3}' \
    "$stage_root/sycl-runtime/linked-libraries.txt" | sort -u)
  if [[ -n "${SIFT_STAGE_PAIR_IMAGE:-}" ]]; then
    while IFS= read -r library; do
      cp -L "$library" "$stage_root/sycl-runtime/lib/"
    done < <(awk -v prefix="$SIFT_STAGE_OPENCV_PREFIX/" \
      '$2 == "=>" && index($3, prefix) == 1 {print $3}' \
      "$stage_root/sycl-runtime/linked-libraries.txt" | sort -u)
  fi
  cp "$compiler_root"/lib/libsycl-*.spv "$stage_root/sycl-runtime/lib/"
  cp -a "$compiler_root/share/doc/compiler/licensing" \
    "$stage_root/sycl-runtime/notices/compiler-licensing"
  cp "$compiler_root/share/doc/compiler/credist.txt" "$stage_root/sycl-runtime/notices/"
  for dependency in umf tcm; do
    notice_root="/opt/intel/oneapi/$dependency/latest/share/doc/$dependency"
    if [[ ! -d "$notice_root" ]]; then
      printf 'Missing runtime dependency notices: %s\n' "$notice_root" >&2
      exit 1
    fi
    cp -a "$notice_root" "$stage_root/sycl-runtime/notices/$dependency"
  done
  printf 'Optional SYCL runtime/test payload: '
  du -sh "$stage_root/sycl-runtime"
fi

(
  cd "$stage_root"
  find . -type f ! -name SHA256SUMS -print0 |
    sort -z |
    xargs -0 sha256sum > SHA256SUMS
)
stage_id="$(sha256sum "$stage_root/SHA256SUMS" | cut -c1-16)"

remote_command="set -eu; parent=\"\$HOME/.local/share/sift-extractor-staging\"; dest=\"\$parent/$stage_id\"; mkdir -p \"\$parent\"; if test -e \"\$dest\"; then printf 'Refusing to overwrite existing stage: %s\\n' \"\$dest\" >&2; exit 1; fi; mkdir \"\$dest\"; tar -xzf - -C \"\$dest\"; cd \"\$dest\"; sha256sum -c SHA256SUMS"
if [[ "$run_tests" -eq 1 ]]; then
  remote_command+='; cmake -S "$dest/libraries/sift-extractor" -B "$dest/build-opencl" -DCMAKE_BUILD_TYPE=Release -DSIFT_ENABLE_SYCL=OFF -DSIFT_ENABLE_OPENCL=ON -DSIFT_BUILD_TESTS=ON -DSIFT_OPENCL_INCLUDE_DIR="$dest"; cmake --build "$dest/build-opencl" --parallel 4; clinfo -l; ctest --test-dir "$dest/build-opencl" --verbose --output-on-failure'
  if [[ -n "${SIFT_STAGE_SYCL_BUILD:-}" ]]; then
    remote_command+='; export LD_LIBRARY_PATH="$dest/sycl-runtime/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"; export ONEAPI_DEVICE_SELECTOR=level_zero:gpu; for test in test_sift_sycl_kernels test_sift_sycl_extract test_sift_sycl_match; do printf "Running %s\n" "$test"; "$dest/sycl-runtime/bin/$test"; done'
    if [[ -n "${SIFT_STAGE_PAIR_IMAGE:-}" ]]; then
      remote_command+='; "$dest/sycl-runtime/bin/validate_sift_pair" "$dest/comparison-input.pgm" "$dest/intel-comparison.json" 10; printf "Intel comparison report: %s\n" "$dest/intel-comparison.json"; cat "$dest/intel-comparison.json"'
    fi
  fi
fi
tar -czf - -C "$stage_root" . | ssh -o StrictHostKeyChecking=yes "$remote" "$remote_command"

printf 'Verified stage: %s:%s/%s\n' "$remote" \
  '$HOME/.local/share/sift-extractor-staging' "$stage_id"
