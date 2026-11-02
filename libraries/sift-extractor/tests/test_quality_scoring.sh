#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
validator="$1"
directory="$(mktemp -d)"
trap 'rm -rf "$directory"' EXIT
jq -n '{width:640,height:480,affine:{type_id:"opencv-matrix",rows:2,cols:3,dt:"d",data:[1,0,10,0,1,20]}}' > "$directory/pair.json"
for transformed in 0 1; do
  jq -n --argjson transformed "$transformed" \
    '{width:640,height:480,positions:{type_id:"opencv-matrix",rows:3,cols:2,dt:"f",
      data:[[100,100],[200,100],[100,200]]|map([.[0]+10*$transformed,.[1]+20*$transformed])|flatten},
      descriptors:{type_id:"opencv-matrix",rows:3,cols:128,dt:"f",
      data:[range(0;3) as $row|range(0;128)|if .==$row then 1 else 0 end]}}' \
    > "$directory/$transformed.json"
done
"$validator" --score-external "$directory/0.json" "$directory/1.json" "$directory/pair.json" "$directory/score.json"
jq -e '.quality.ratio_matches==3 and .quality.ground_truth_inliers_3px==3 and .quality.inlier_rmse_px==0' "$directory/score.json" >/dev/null
for mutation in '.descriptors.cols=127' '.width=639' '.positions.data[0]=-1' \
    '.descriptors.data=([range(0;384)]|map(0))' '.positions.rows=32769'; do
  jq "$mutation" "$directory/0.json" > "$directory/invalid.json"
  if "$validator" --score-external "$directory/invalid.json" "$directory/1.json" \
      "$directory/pair.json" "$directory/rejected.json" > "$directory/error.log" 2>&1; then
    printf 'Accepted invalid input: %s\n' "$mutation" >&2
    exit 1
  fi
done
jq '.positions.rows=0|.positions.data=[]|.descriptors.rows=0|.descriptors.data=[]' \
  "$directory/0.json" > "$directory/empty.json"
"$validator" --score-external "$directory/empty.json" "$directory/empty.json" "$directory/pair.json" "$directory/empty-score.json"
jq -e '.quality.ratio_matches==0 and .quality.ground_truth_inliers_3px==0 and .quality.inlier_rmse_px == -1' "$directory/empty-score.json" >/dev/null
printf 'Known-transform scoring, empty results and five invalid feature cases passed\n'