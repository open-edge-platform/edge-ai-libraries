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
jq 'del(.affine)|.homography={type_id:"opencv-matrix",rows:3,cols:3,dt:"d",
  data:[1,0,10,0,1,20,0.001,0,1]}' "$directory/pair.json" > "$directory/projective.json"
jq '.positions.data=[100,120/1.1,175,100,100,200]' "$directory/0.json" > "$directory/projected.json"
for multiplier in 1 -1 1e-100 1e100; do
  jq --argjson multiplier "$multiplier" '.homography.data|=map(.*$multiplier)' \
    "$directory/projective.json" > "$directory/scaled-projective.json"
  "$validator" --score-external "$directory/0.json" "$directory/projected.json" \
    "$directory/scaled-projective.json" "$directory/projective-score.json"
  jq -e '.geometry_model=="homography" and (.quality | .ratio_matches==3 and
    .ground_truth_inliers_3px==3 and .inlier_rmse_px<0.0001 and
    .unprojectable_ratio_matches==0)' "$directory/projective-score.json" >/dev/null
done
jq '.homography.data=[1,0,10,0,1,20,0,0,1]' "$directory/projective.json" > "$directory/affine-homography.json"
"$validator" --score-external "$directory/0.json" "$directory/1.json" \
  "$directory/affine-homography.json" "$directory/affine-homography-score.json"
jq -e '.quality | .ground_truth_inliers_3px==3 and .inlier_rmse_px<1e-10 and
  .unprojectable_ratio_matches==0' "$directory/affine-homography-score.json" >/dev/null
jq '.homography.data=[0,0,1,0,1,0,1,0,0]' "$directory/projective.json" > "$directory/zero-bottom-right.json"
jq '.positions.data=[0.01,1,0.005,0.5,0.01,2]' "$directory/0.json" > "$directory/reciprocal.json"
"$validator" --score-external "$directory/0.json" "$directory/reciprocal.json" \
  "$directory/zero-bottom-right.json" "$directory/reciprocal-score.json"
jq -e '.quality | .ground_truth_inliers_3px==3 and .inlier_rmse_px<1e-8 and
  .unprojectable_ratio_matches==0' "$directory/reciprocal-score.json" >/dev/null
jq '.homography.data=[1,0,0,0,1,0,0.005,0,0.5]' "$directory/projective.json" > "$directory/boundary.json"
jq '.positions.data=[103,100,200/1.5,100/1.5,103.0001,200]' "$directory/0.json" > "$directory/boundary-points.json"
"$validator" --score-external "$directory/0.json" "$directory/boundary-points.json" \
  "$directory/boundary.json" "$directory/boundary-score.json"
jq -e '.quality | .ratio_matches==3 and .ground_truth_inliers_3px==2 and
  .inlier_rmse_px>2.12 and .inlier_rmse_px<2.13 and
  .unprojectable_ratio_matches==0' "$directory/boundary-score.json" >/dev/null
jq '.homography.data=[1,0,0,0,1,0,0.01,0,-1]' "$directory/projective.json" > "$directory/horizon.json"
"$validator" --score-external "$directory/0.json" "$directory/0.json" \
  "$directory/horizon.json" "$directory/horizon-score.json"
jq -e '.quality | .ratio_matches==3 and .ground_truth_inliers_3px==1 and
  .unprojectable_ratio_matches==2 and .inlier_fraction<0.334 and
  .inlier_rmse_px==0' "$directory/horizon-score.json" >/dev/null
for mutation in '.homography.rows=3000000' '.homography.cols=4' '.homography.dt="f"' \
    '.homography.data=[1,0,0,0,0,0,0,0,1]' '.homography.data=([range(0;9)]|map(0))' \
    '.homography.data=[1,0,0,0,1e-20,0,0,0,1]' \
    '.homography.data|=.[0:8]' '.homography.data[0]="invalid"' \
    '.affine=.homography' 'del(.homography)'; do
  jq "$mutation" "$directory/projective.json" > "$directory/invalid-pair.json"
  if "$validator" --score-external "$directory/0.json" "$directory/1.json" \
      "$directory/invalid-pair.json" "$directory/rejected.json" > "$directory/error.log" 2>&1; then
    printf 'Accepted invalid geometry: %s\n' "$mutation" >&2
    exit 1
  fi
done
jq '.padding=("x"*1048576)' "$directory/projective.json" > "$directory/oversized-pair.json"
if "$validator" --score-external "$directory/0.json" "$directory/1.json" \
    "$directory/oversized-pair.json" "$directory/rejected.json" > "$directory/error.log" 2>&1; then
  printf 'Accepted oversized pair report\n' >&2
  exit 1
fi
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
printf 'Affine/projective scoring, spatial support, horizon handling and malformed-input checks passed\n'