// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { OnEvent } from '@nestjs/event-emitter';
import {
  SubscribeMessage,
  WebSocketGateway,
  WebSocketServer,
} from '@nestjs/websockets';
import { Logger } from '@nestjs/common';
import { Server, Socket } from 'socket.io';
import {
  PipelineEvents,
  SearchEvents,
  SummaryStreamChunk,
} from 'src/events/Pipeline.events';
import {
  SocketEvent,
  SocketFrameSummarySyncDTO,
  SocketStateSyncPayload,
} from 'src/events/socket.events';
import { SearchEntity } from 'src/search/model/search.entity';
import { SearchQuery } from 'src/search/model/search.model';
import { UiService } from 'src/state-manager/services/ui.service';

@WebSocketGateway({
  cors: {
    origin: '*',
  },
  path: '/ws/',
})
export class EventsGateway {
  @WebSocketServer()
  server: Server;

  private logger = new Logger(EventsGateway.name);

  constructor(private $ui: UiService) {}

  @OnEvent(SocketEvent.SEARCH_NOTIFICATION)
  searchNotification() {
    this.logger.log('Emitting search:sync notification');
    this.server.emit('search:sync');
  }

  @OnEvent(SocketEvent.SEARCH_UPDATE)
  searchUpdate(payload: SearchQuery) {
    this.logger.log(`Emitting search:update for queryId=${payload.queryId}`);
    this.server.emit('search:update', payload);
  }

  @OnEvent(SocketEvent.STATE_SYNC)
  syncState(payload: SocketStateSyncPayload) {
    const { stateId } = payload;

    const uiState = this.$ui.getUiState(stateId);

    if (uiState) {
      this.server.to(stateId).emit(`summary:sync/${stateId}`, uiState);
    }
  }

  @OnEvent(SocketEvent.STATUS_SYNC)
  stateStatusSync(payload: SocketStateSyncPayload) {
    const { stateId } = payload;

    const stateStatus = this.$ui.getStateStatus(stateId);

    if (stateStatus) {
      this.server
        .to(stateId)
        .emit(`summary:sync/${stateId}/status`, stateStatus);
    }
  }

  @OnEvent(SocketEvent.CHUNKING_DATA)
  syncChunkingData(stateId: string) {
    const chunks = this.$ui.getUIChunks(stateId);
    const frames = this.$ui.getUIFrames(stateId);

    this.server
      .to(stateId)
      .emit(`summary:sync/${stateId}/chunks`, { chunks, frames });
  }

  @OnEvent(SocketEvent.FRAME_SUMMARY_SYNC)
  frameSummarySync({ frameKey, stateId }: SocketFrameSummarySyncDTO) {
    const frameSummary = this.$ui.getSummaryData(stateId, frameKey);

    if (frameSummary) {
      this.server.to(stateId).emit(`summary:sync/${stateId}/frameSummary`, {
        stateId,
        ...frameSummary,
      });
    }
  }

  @OnEvent(SocketEvent.CONFIG_SYNC)
  stateConfigSync(stateId: string) {
    const inferenceConfig = this.$ui.getInferenceConfig(stateId);

    this.server
      .to(stateId)
      .emit(`summary:sync/${stateId}/inferenceConfig`, inferenceConfig);
  }

  @OnEvent(SocketEvent.SUMMARY_SYNC)
  summarySync({ stateId, summary }: { stateId: string; summary: string }) {
    this.server
      .to(stateId)
      .emit(`summary:sync/${stateId}/summary`, { stateId, summary });
  }

  @OnEvent(PipelineEvents.SUMMARY_STREAM)
  summaryStream({ stateId, streamChunk }: SummaryStreamChunk) {
    this.server
      .to(stateId)
      .emit(`summary:sync/${stateId}/summaryStream`, streamChunk);
  }

  @SubscribeMessage('join')
  async handleJoin(client: Socket, roomName: string) {
    this.logger.log(`Client ${client.id} joining room ${roomName}`);
    await client.join(roomName);
  }
}
