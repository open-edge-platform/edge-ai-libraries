#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
if (( $# < 3 )); then
  printf 'Usage: %s VALIDATOR CORPUS_DIR NEW_OUTPUT_DIR [PROFILE ...]\n' "$0" >&2
  exit 2
fi
validator="$(realpath "$1")"
corpus="$(realpath "$2")"
output="$3"
shift 3
profiles=(identity rotation30 rotation90 scale_half scale_large illumination blur combined)
if (( $# )); then profiles=("$@"); fi
command -v jq >/dev/null
mkdir "$output"
output="$(realpath "$output")"
mapfile -d '' images < <(find "$corpus" -maxdepth 1 -type f \( -name '*.pgm' -o -name '*.png' -o -name '*.jpg' \) -print0 | sort -z)
if (( ${#images[@]} == 0 )); then
  printf 'No corpus images found\n' >&2
  exit 2
fi
sha256sum "$validator" "${images[@]}" > "$output/inputs.sha256"
failures=0
for image in "${images[@]}"; do
  name="$(basename "$image")"
  for profile in "${profiles[@]}"; do
    case "$profile" in
      identity) rotation=0; scale=1; gain=1; bias=0; blur=0 ;;
      rotation30) rotation=30; scale=1; gain=1; bias=0; blur=0 ;;
      rotation90) rotation=90; scale=1; gain=1; bias=0; blur=0 ;;
      scale_half) rotation=0; scale=0.5; gain=1; bias=0; blur=0 ;;
      scale_large) rotation=0; scale=1.5; gain=1; bias=0; blur=0 ;;
      illumination) rotation=0; scale=1; gain=0.6; bias=20; blur=0 ;;
      blur) rotation=0; scale=1; gain=1; bias=0; blur=2 ;;
      combined) rotation=30; scale=0.85; gain=1; bias=0; blur=0 ;;
      *) printf 'Unknown profile: %s\n' "$profile" >&2; exit 2 ;;
    esac
    directory="$output/$name-$profile"
    mkdir "$directory"
    jq -n --argjson rotation "$rotation" --argjson scale "$scale" \
      --argjson gain "$gain" --argjson bias "$bias" --argjson blur "$blur" \
      '{rotationDegrees:$rotation,scaleFactor:$scale,gain:$gain,bias:$bias,blurSigma:$blur,nfeatures:0}' \
      > "$directory/config.json"
    if "$validator" "$image" "$directory/pair.json" 0 "$directory/config.json" quality-export \
        > "$directory/pair.log" 2>&1; then
      status=ok
      # Reject saturated / capacity-capped exports before scoring aggregates.
      if [[ -f "$directory/pair.json" ]]; then
        saturated="$(jq -r '
          def capped($node; $cap):
            (($node.first_features // 0) >= $cap)
            or (($node.second_features // 0) >= $cap);
          (.capacity // 32768) as $cap |
          (.sycl_capacity // 32768) as $scap |
          if (capped(.opencv_cpu_default; $cap)
              or capped(.opencl_prototype; $cap)
              or capped(.sycl_reference; $scap))
            then "yes" else "no" end
        ' "$directory/pair.json" 2>/dev/null || echo unknown)"
        if [[ "$saturated" == "yes" ]]; then
          status=export_saturated
          failures=$((failures + 1))
        elif [[ "$saturated" == "unknown" ]]; then
          status=export_check_failed
          failures=$((failures + 1))
        fi
      fi
    else
      status=pair_failed
      failures=$((failures + 1))
    fi
    jq -n --arg image "$name" --arg profile "$profile" --arg status "$status" \
      '{image:$image,profile:$profile,status:$status}' > "$directory/status.json"
    printf '%s %s: %s\n' "$name" "$profile" "$status"
  done
done
jq -s '.' "$output/"*/status.json > "$output/status.json"
printf 'Cases: %s; failed executions: %s\n' "$(jq length "$output/status.json")" "$failures"
if (( failures == 0 )); then
  for directory in "$output/"*/; do
    jq -s '{image:.[0].image,profile:.[0].profile,status:.[0].status,
      metrics:{opencv:.[1].opencv_cpu_default,opencl:.[1].opencl_prototype,
      sycl:.[1].sycl_reference}}' \
      "$directory/status.json" "$directory/pair.json"
  done | jq -s '.' > "$output/cases.json"
  jq 'def median: sort|. as $values|length as $count|
      ($values[($count/2|floor)]+$values[(($count-1)/2|floor)])/2;
    [group_by(.profile)[] | . as $cases |
    ["opencv","opencl","sycl"][] as $backend |
    [$cases[].metrics[$backend]] as $metrics |
    ($metrics|map(.ground_truth_inliers_3px)|add) as $inliers |
    ($metrics|map(.ratio_matches)|add) as $matches |
    {profile:$cases[0].profile,backend:$backend,cases:($metrics|length),total_inliers:$inliers,
    median_inliers:($metrics|map(.ground_truth_inliers_3px)|median),
    pooled_inlier_fraction:(if $matches>0 then $inliers/$matches else null end),
    pooled_inlier_rmse_px:(if $inliers>0 then
      (($metrics|map(.ground_truth_inliers_3px*.inlier_rmse_px*.inlier_rmse_px)|add)/$inliers|sqrt)
      else null end),
    zero_inlier_cases:($metrics|map(select(.ground_truth_inliers_3px==0))|length)}]' \
    "$output/cases.json" > "$output/summary.json"
fi
(( failures == 0 ))
