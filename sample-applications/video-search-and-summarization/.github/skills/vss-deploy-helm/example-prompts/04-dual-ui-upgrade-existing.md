<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

I currently have the `vss` release running in unified mode (`unified_summary_search.yaml`) in namespace `vss-deployment`, but I actually want separate Summary and Search UIs like `setup.sh --dual` gives you, reachable at `/summary/` and `/search/`. Can I just `helm upgrade` to the dual override files, or do I need to do something else first?
