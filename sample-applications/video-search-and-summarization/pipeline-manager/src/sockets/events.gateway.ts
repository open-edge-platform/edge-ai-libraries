import { OnEvent } from '@nestjs/event-emitter';
import {
  SubscribeMessage,
  WebSocketGateway,
  WebSocketServer,
} from '@nestjs/websockets';
import { Server, Socket } from 'socket.io';
import { PipelineEvents, SummaryStreamChunk } from 'src/events/Pipeline.events';
import {
  SocketEvent,
  SocketFrameSummarySyncDTO,
  SocketStateSyncPayload,
} from 'src/events/socket.events';
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

  constructor(private $ui: UiService) {}

  @OnEvent(SocketEvent.STATE_SYNC)
  syncState(payload: SocketStateSyncPayload) {
    const { stateId } = payload;

    const uiState = this.$ui.getUiState(stateId);

    if (uiState) {
      this.server.to(stateId).emit(`sync/${stateId}`, uiState);
    }
  }

  @OnEvent(SocketEvent.STATUS_SYNC)
  stateStatusSync(payload: SocketStateSyncPayload) {
    const { stateId } = payload;

    const stateStatus = this.$ui.getStateStatus(stateId);

    if (stateStatus) {
      this.server.to(stateId).emit(`sync/${stateId}/status`, stateStatus);
    }
  }

  @OnEvent(SocketEvent.CHUNKING_DATA)
  syncChunkingData(stateId: string) {
    const chunks = this.$ui.getUIChunks(stateId);
    const frames = this.$ui.getUIFrames(stateId);

    this.server.to(stateId).emit(`sync/${stateId}/chunks`, { chunks, frames });
  }

  @OnEvent(SocketEvent.FRAME_SUMMARY_SYNC)
  frameSummarySync({ frameKey, stateId }: SocketFrameSummarySyncDTO) {
    const frameSummary = this.$ui.getSummaryData(stateId, frameKey);

    if (frameSummary) {
      this.server
        .to(stateId)
        .emit(`sync/${stateId}/frameSummary`, { stateId, ...frameSummary });
    }
  }

  @OnEvent(SocketEvent.CONFIG_SYNC)
  stateConfigSync(stateId: string) {
    const inferenceConfig = this.$ui.getInferenceConfig(stateId);

    this.server
      .to(stateId)
      .emit(`sync/${stateId}/inferenceConfig`, inferenceConfig);
  }

  @OnEvent(SocketEvent.SUMMARY_SYNC)
  summarySync({ stateId, summary }: { stateId: string; summary: string }) {
    this.server
      .to(stateId)
      .emit(`sync/${stateId}/summary`, { stateId, summary });
  }

  @OnEvent(PipelineEvents.SUMMARY_STREAM)
  summaryStream({ stateId, streamChunk }: SummaryStreamChunk) {
    this.server.to(stateId).emit(`sync/${stateId}/summaryStream`, streamChunk);
  }

  @SubscribeMessage('join')
  handleJoin(client: Socket, roomName: string) {
    client.join(roomName);
  }

  @SubscribeMessage('stop')
  handleStop(client: any, payload: { stateId: string }): string {
    return 'Pipeline stop registered';
  }

  @SubscribeMessage('message')
  handleMessage(client: any, payload: any): string {
    return 'Hello world!';
  }
}
