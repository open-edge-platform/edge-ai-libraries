#!/bin/bash

# This script creates the `mr_postgres` and `mr_minio` directories in the ${MR_INSTALL_PATH}/data directory, 
# adds the MR_USER_NAME to the system, and changes the ownership of the directories 
# to the MR_USER_NAME. These directories are used as the persistent location
# for model metadata and artifacts.

# shellcheck disable=SC1091
source ../docker/.env

psql_data_dir_path=${MR_INSTALL_PATH}/data/mr_postgres
minio_data_dir_path=${MR_INSTALL_PATH}/data/mr_minio

user_name="$MR_USER_NAME"
user_id="$MR_UID"

mkdir -p "$psql_data_dir_path"
mkdir -p "$minio_data_dir_path"

if ! id -u "$user_name" &> /dev/null; then
  useradd -u "$user_id" "$user_name"
fi

# Set the ownership of the `mr_postgres` and `mr_minio` directories to the MR_USER_NAME user
chown "$user_name:$user_name" "$psql_data_dir_path"
chown "$user_name:$user_name" "$minio_data_dir_path"
