<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

I want to add a new `health-report` feature to the VSS pipeline-manager. It should expose a `GET /health-report` endpoint that returns a simple status object with `uptimeSeconds` and `videoCount` fields. No database persistence needed - just scaffold the module, controller, and service the way this repo already does it.
