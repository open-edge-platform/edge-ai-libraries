# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

for i in $(env | grep APP_)
do
  key=$(echo $i | cut -d '=' -f 1)
  value=$(echo $i | cut -d '=' -f 2-)
  echo $key=$value
  
  find /usr/share/nginx/html -type f \( -name '*.js' -o -name '*.css' \) -exec sed -i "s|${key}|${value}|g" '{}' +
done
