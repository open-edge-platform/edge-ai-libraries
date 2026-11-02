<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

Extend the VSS orchestrator with a `transcription-review` module. As review progress changes it should emit a socket event so the UI updates live - add a new value to `src/events/socket.events.ts`, emit it from the service, and add the corresponding `@OnEvent` handler in `sockets/events.gateway.ts` that broadcasts `transcription-review:update` to clients, following the pattern used for `SocketEvent.SEARCH_UPDATE`.
