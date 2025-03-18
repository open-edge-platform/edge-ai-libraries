#!/bin/bash

#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

# This shell script makes the `mr_models` directory in the project's root directory,
# creates a new user based on the value of the `EVAM_USER` environment variable,
# and changes the ownership of the `mr_models` directory to the new user. This
# directory is used as the location for model artifacts downloaded from the
# model registry microservice by EVAM.


source ../docker/.env

current_working_dir=$(pwd)
parent_dir=$(dirname "$current_working_dir")
target_dir="mr_models"
dir_path="$parent_dir/$target_dir"

# Create the target_dir (mr_models) directory
mkdir -p "$dir_path"

if [[ -d "$parent_dir/$target_dir" ]]; then
    echo "The '$target_dir' directory was created in $parent_dir."
else
    echo "The '$target_dir' directory does not exist in $parent_dir."
fi

user_name="$EVAM_USER"
user_id="$EVAM_UID"

# Add the EVAM_USER to the host system
if ! id -u "$user_name" &> /dev/null; then
  useradd -u "$user_id" "$user_name"
  echo "The user account '$user_name' was created."
fi

# Set the $target_dir (mr_models) directory ownership to the EVAM_USER
chown "$user_name:$user_name" "$dir_path"

owner=$(stat -c "%U" "$dir_path")

if [[ "$owner" == "$user_name" ]]; then
    echo "The '$target_dir' directory is owned by $user_name."
else
    echo "The '$target_dir' directory is not owned by $user_name. The owner is: $owner"
fi
