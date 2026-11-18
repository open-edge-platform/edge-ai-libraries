// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { OnEvent } from '@nestjs/event-emitter';
import {
  SubscribeMessage,
  WebSocketGateway,
  WebSocketServer,
  OnGatewayDisconnect,
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
import { LiveStreamInfo } from 'src/streams/models/stream.model';
import { StreamPollerService } from 'src/streams/services/stream-poller.service';

@WebSocketGateway({
  cors: {
    origin: '*',
  },
  path: '/ws/',
})
export class EventsGateway implements OnGatewayDisconnect {
  @WebSocketServer()
  server: Server;

  private logger = new Logger(EventsGateway.name);

  /**
   * Sockets currently in the live-streams room.
   *
   * Tracked explicitly so a disconnect can decrement the poller. socket.io
   * removes a disconnecting socket from its rooms automatically, but it does
   * not tell us which rooms it was in by the time `handleDisconnect` runs.
   * Without this the poller's subscriber count would only ever go up, and the
   * poll loop would outlive the last viewer.
   */
  private streamSubscribers = new Set<string>();

  constructor(
    private $ui: UiService,
    private $streamPoller: StreamPollerService,
  ) {}

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

  // -- Live streams --------------------------------------------------------

  /**
   * Broadcast live-stream state to viewers only.
   *
   * Scoped to the room rather than `server.emit` so deployments that never
   * open the Live Streams modal - and Live Video Search, which shares this
   * image - receive nothing.
   */
  @OnEvent(SocketEvent.STREAMS_SYNC)
  streamsSync(payload: LiveStreamInfo[]) {
    this.server.to(StreamPollerService.ROOM).emit('streams:sync', payload);
  }

  @SubscribeMessage('streams:subscribe')
  async handleStreamsSubscribe(client: Socket) {
    if (this.streamSubscribers.has(client.id)) return;

    this.streamSubscribers.add(client.id);
    await client.join(StreamPollerService.ROOM);
    this.$streamPoller.addSubscriber();
    this.logger.log(`Client ${client.id} subscribed to live streams`);
  }

  @SubscribeMessage('streams:unsubscribe')
  async handleStreamsUnsubscribe(client: Socket) {
    if (!this.streamSubscribers.delete(client.id)) return;

    await client.leave(StreamPollerService.ROOM);
    this.$streamPoller.removeSubscriber();
    this.logger.log(`Client ${client.id} unsubscribed from live streams`);
  }

  /**
   * A viewer closing the tab must release its poller subscription, otherwise
   * the poll loop runs forever against dataprep with nobody listening.
   */
  handleDisconnect(client: Socket) {
    if (this.streamSubscribers.delete(client.id)) {
      this.$streamPoller.removeSubscriber();
    }
  }
}
