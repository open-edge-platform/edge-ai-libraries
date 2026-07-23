<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

We need a new `/manager/clips` endpoint in pipeline-manager that lets clients request a short clip around a timestamp for an already-uploaded video. Scaffold the NestJS module, a thin controller, and a service layer for it, and have it inject `VideoService` from `VideoUploadModule` the same way `SummaryModule` does.
