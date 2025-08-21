# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FROM intel/dlstreamer-pipeline-server:3.0.0

COPY requirements.txt . 
RUN pip install --no-cache-dir -r requirements.txt

COPY ../src /home/pipeline-server/gvapython/publisher/
COPY ../resources/conf/config.json /home/pipeline-server/config.json

EXPOSE 8080