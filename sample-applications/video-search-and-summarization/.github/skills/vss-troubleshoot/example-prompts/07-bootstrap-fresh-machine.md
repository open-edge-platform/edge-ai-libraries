<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

I ran `source setup.sh --summary-and-search` and the containers all say they're up, but hitting `http://localhost:12345` in the browser just spins and `curl http://localhost:12345/manager/health` times out with no response at all. Can you figure out why the gateway isn't answering and what's actually broken?
