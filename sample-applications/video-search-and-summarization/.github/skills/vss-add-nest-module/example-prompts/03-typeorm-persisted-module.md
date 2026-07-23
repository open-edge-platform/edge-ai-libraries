<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

Add a `notifications` module to pipeline-manager. It needs a controller, a service, a TypeORM entity called `NotificationEntity` (fields: `dbId`, `stateId`, `message`, `read` boolean), and a `NotificationsDbService` for repository access, following the same pattern `search/search.module.ts` uses for `SearchEntity`.
