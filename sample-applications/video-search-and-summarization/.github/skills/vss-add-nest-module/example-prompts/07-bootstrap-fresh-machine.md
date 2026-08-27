<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

Add a `watchlist` module to pipeline-manager. It should let clients flag a video for follow-up review, with a controller exposing `POST /watchlist/:videoId` and `GET /watchlist`, a service layer, and a TypeORM entity called `WatchlistEntity` (fields: `dbId`, `videoId`, `reason`, `createdAt`) persisted through a `WatchlistDbService`, following the same repository pattern `search/search.module.ts` uses for `SearchEntity`.
