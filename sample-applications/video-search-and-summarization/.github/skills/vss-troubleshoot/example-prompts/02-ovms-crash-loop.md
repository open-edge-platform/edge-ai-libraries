<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

I brought up summary mode with `source setup.sh --summary`, but `ovms-service` keeps restarting with exit code 1 and `pipeline-manager` never becomes healthy. `docker ps -a` shows `ovms-service` crash-looping, and `curl http://localhost:8300/v2/health/ready` just refuses the connection. What should I check first and what fixes are realistic here?
