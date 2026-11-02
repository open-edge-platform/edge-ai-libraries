<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

We're adding a full `recommendations` capability to pipeline-manager: a REST module with request/response DTOs and Swagger decorators, a TypeORM entity for storing generated recommendations, a queue service that processes recommendation jobs on `AppEvents.FAST_TICK`, and it should import `VideoUploadModule` and `StateManagerModule` via DI to reuse `VideoService` and `StateService`. It also needs a new config key under `recommendations.maxConcurrent` read through `ConfigService`. Please scaffold this the real VSS way, not generic NestJS boilerplate.
