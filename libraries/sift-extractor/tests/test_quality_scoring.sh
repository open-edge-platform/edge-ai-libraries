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
jq -e '.quality | .ratio_matches==3 and .ground_truth_inliers_3px==3 and .inlier_rmse_px==0 and
  .first_distinct_positions==3 and .second_distinct_positions==3 and
  .first_duplicate_records==0 and .second_duplicate_records==0 and
  .inlier_distinct_first_positions==3 and .inlier_distinct_second_positions==3' "$directory/score.json" >/dev/null
for transformed in 0 1; do
  jq '.positions.rows+=1|.positions.data+=.positions.data[0:2]|
    .descriptors.rows+=1|.descriptors.data+=.descriptors.data[0:128]' \
    "$directory/$transformed.json" > "$directory/duplicate-$transformed.json"
done
"$validator" --score-external "$directory/duplicate-0.json" "$directory/1.json" "$directory/pair.json" "$directory/duplicate-query-score.json"
jq -e '.quality | .ratio_matches==4 and .ground_truth_inliers_3px==4 and .inlier_rmse_px==0 and
  .first_distinct_positions==3 and .first_duplicate_records==1 and .second_duplicate_records==0 and
  .inlier_distinct_first_positions==3 and .inlier_distinct_second_positions==3' "$directory/duplicate-query-score.json" >/dev/null
"$validator" --score-external "$directory/0.json" "$directory/duplicate-1.json" "$directory/pair.json" "$directory/duplicate-target-score.json"
jq -e '.quality | .ratio_matches==2 and .ground_truth_inliers_3px==2 and .inlier_rmse_px==0 and
  .second_distinct_positions==3 and .second_duplicate_records==1 and
  .inlier_distinct_first_positions==2 and .inlier_distinct_second_positions==2' "$directory/duplicate-target-score.json" >/dev/null
for transformed in 0 1; do
  jq '.positions.data[2:4]=.positions.data[0:2]' "$directory/$transformed.json" \
    > "$directory/colocated-$transformed.json"
done
"$validator" --score-external "$directory/colocated-0.json" "$directory/colocated-1.json" "$directory/pair.json" "$directory/colocated-score.json"
jq -e '.quality | .ratio_matches==3 and .ground_truth_inliers_3px==3 and .inlier_rmse_px==0 and
  .first_distinct_positions==2 and .second_distinct_positions==2 and
  .first_duplicate_records==0 and .second_duplicate_records==0 and
  .inlier_distinct_first_positions==2 and .inlier_distinct_second_positions==2' "$directory/colocated-score.json" >/dev/null
jq '.positions.data[6]+=1' "$directory/duplicate-0.json" > "$directory/many-to-one.json"
"$validator" --score-external "$directory/many-to-one.json" "$directory/1.json" "$directory/pair.json" "$directory/many-to-one-score.json"
jq -e '.quality | .ratio_matches==4 and .ground_truth_inliers_3px==4 and .inlier_rmse_px==0.5 and
  .first_distinct_positions==4 and .first_duplicate_records==0 and
  .inlier_distinct_first_positions==4 and .inlier_distinct_second_positions==3' "$directory/many-to-one-score.json" >/dev/null
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
jq -e '.quality | .ratio_matches==0 and .ground_truth_inliers_3px==0 and .inlier_rmse_px == -1 and
  .first_distinct_positions==0 and .second_distinct_positions==0 and
  .first_duplicate_records==0 and .second_duplicate_records==0 and
  .inlier_distinct_first_positions==0 and .inlier_distinct_second_positions==0' "$directory/empty-score.json" >/dev/null
printf 'Known-transform scoring, spatial support, duplicate records, empty results and five invalid feature cases passed\n'