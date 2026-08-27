<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

I want a leaner MCP surface for a demo: only `GET /app/features` as a resource and `POST /search/query` as a tool, under server name `vss_search_mcp` and prefix `vss`. I'll call the file `mcp/my-search-filter.json`. Since I'm running via `docker compose up`, what else besides `FILTER_FILE_PATH` do I need to change so the container actually sees this file?
