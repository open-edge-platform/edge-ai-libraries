# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Several sources per pool: profiles, bindings, and how one replaces another.

The rule everything here follows: a source is fixed in what it embeds with. A
different model *or* different parameters is a different source, and moving a
pool from one to the other is a replacement the state machine carries out once
the new one has caught up. `AssetLibrary` calls into these modules at a handful
of points (create, attach, sync, retrieve, delete); the rules live here.

- `binding`        -- serving states, and the effective state a source's
                      `enabled` switch lays over them
- `state_machine`  -- PREPARING → SERVING → DEPRECATED, planned purely, applied
                      in one place
- `updates`        -- what a caller may change, and the checks on `replaces`
- `profile`        -- what produced a source's records, fixed at creation
- `exposure`       -- which projections a pool retrieves through, and the
                      provenance stamped on records
- `frozen`         -- deletes reaching bindings that hold no projection
- `backfill`       -- a preparing binding's backlog, written in batches
"""
