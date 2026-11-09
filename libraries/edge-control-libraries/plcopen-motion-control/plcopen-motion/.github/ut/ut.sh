#!/bin/bash

cd build/test

test_list=("function_block_test" "online_scurve_test" "offline_scurve_test" "planner_test")

for program in "${test_list[@]}"; do
  ./$program

  exit_status=$?

  if [ "$exit_status" -ne 0 ]; then
    echo "Error: $program returned non-zero exit status"
    exit "$exit_status"
  fi
done

echo "All programs executed successfully"
