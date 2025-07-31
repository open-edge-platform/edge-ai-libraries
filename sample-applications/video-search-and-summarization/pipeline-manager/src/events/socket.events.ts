// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
export enum SocketEvent {
  STATE_SYNC = 'socket.stateSync',
  STATE_SYNC_PARTIAL = 'socket.stateSyncPartial',

  CONFIG_SYNC = 'socket.state.config',

  STATUS_SYNC = 'socket.state.status',

  AUDIO_SYNC = 'socket.state.audio',

  CHUNKING_DATA = 'socket.state.chunking',

  SUMMARY_SYNC = 'socket.summary',
  SUMMARY_CHUNK = 'soket.summary.chunk',

  FRAME_SUMMARY_SYNC = 'socket.frame.summary',

  SEARCH_NOTIFICATION = 'socket.search.notification',
  SEARCH_UPDATE = 'socket.search.update',
}

export interface SocketStateSyncPayload {
  stateId: string;
}

export interface SocketFrameSummarySyncDTO extends SocketStateSyncPayload {
  frameKey: string;
}
