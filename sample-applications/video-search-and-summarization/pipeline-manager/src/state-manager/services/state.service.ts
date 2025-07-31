// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Injectable, Logger } from '@nestjs/common';
import {
  ModelInfo,
  State,
  StateActionStatus,
  StateChunk,
  StateChunkFrame,
} from '../models/state.model';
import { v4 as uuidV4 } from 'uuid';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { SocketEvent } from 'src/events/socket.events';
import { SystemConfig } from 'src/video-upload/models/upload.model';
import { ChunkQueue } from 'src/evam/models/message-broker.model';
import { ConfigService } from '@nestjs/config';
import { StateDbService } from './state-db.service';
import {
  AudioTranscriptDTO,
  AudioTranscriptsParsed,
} from 'src/audio/models/audio.model';
import { Video } from 'src/video-upload/models/video.model';
import { SummaryPipelineSampling } from 'src/summary/models/summary-pipeline.model';
import { PipelineEvents } from 'src/events/Pipeline.events';
import { VideoEntity } from 'src/video-upload/models/video.entity';
import { AppEvents } from 'src/events/app.events';

@Injectable()
export class StateService {
  private states: Map<string, State> = new Map();

  constructor(
    private emitter: EventEmitter2,
    private $config: ConfigService,
    private $stateDb: StateDbService,
  ) {}

  async init(videos: VideoEntity[]) {
    const states = await this.$stateDb.getAllStates();
    states.forEach((state) => {
      const video = videos.find((v) => v.videoId === state.videoId);

      if (video) {
        this.states.set(state.stateId, {
          ...state,
          video: video,
        });
      }
    });
    console.log('StateService initialized with', this.states.size, 'states');
  }

  fetchAll(): State[] {
    return Array.from(this.states.values());
  }

  async saveToDB(stateId: string) {
    if (this.states.has(stateId)) {
      const state = this.states.get(stateId);
      if (state) {
        try {
          const res = await this.$stateDb.updateState(stateId, state);
          Logger.log('State saved to DB:', res);
        } catch (error) {
          Logger.error('Error saving state to DB:', error);
        }
      }
    }
  }

  exists(stateId: string) {
    return this.states.has(stateId);
  }

  fetch(stateId: string): State | undefined {
    return this.states.get(stateId);
  }

  fetchChunk(stateId: string, chunkId: string): StateChunk | null {
    if (this.states.has(stateId)) {
      return this.states.get(stateId)!.chunks[chunkId] ?? null;
    }
    return null;
  }

  fetchFrame(stateId: string, frameId: string): StateChunkFrame | null {
    return this.states.get(stateId)?.frames[frameId] ?? null;
  }

  has(stateId: string): boolean {
    return this.states.has(stateId);
  }

  update(state: State) {
    this.states.set(state.stateId, state);
    this.syncSocket(state.stateId);
  }

  audioTrigger(stateId: string, audioRequest: AudioTranscriptDTO) {
    if (this.states.has(stateId)) {
      this.states.get(stateId)!.audio = {
        device: audioRequest.device,
        model: audioRequest.model_name,
        status: StateActionStatus.IN_PROGRESS,
        transcript: [],
      };
    }
  }

  audioComplete(stateId: string, audioResult: AudioTranscriptsParsed) {
    if (this.states.has(stateId)) {
      this.states.get(stateId)!.audio!.status = StateActionStatus.COMPLETE;
      this.states.get(stateId)!.audio!.transcriptPath =
        audioResult.transcriptPath;
      this.states.get(stateId)!.audio!.transcript = audioResult.transcripts;
    }
  }

  addChunk(stateId: string, chunk: ChunkQueue) {
    if (this.states.has(stateId)) {
      const createdAt: string = new Date().toISOString();
      const chunkId = chunk.chunkId.toString();
      const stateChunk: StateChunk = {
        chunkId,
      };

      const frames = chunk.frames.reduce(
        (acc: Record<string, StateChunkFrame>, frame) => {
          const frameId: string = frame.frameId.toString();
          acc[frameId] = {
            createdAt,
            frameId,
            chunkId,
            frameUri: frame.imageUri,
          };

          if (frame.metadata) {
            acc[frameId].metadata = frame.metadata;
          }

          return acc;
        },
        {},
      );

      const currentFrames = this.states.get(stateId)!.frames ?? {};

      this.states.get(stateId)!.chunks[stateChunk.chunkId] = stateChunk;
      this.states.get(stateId)!.frames = { ...currentFrames, ...frames };
      this.syncSocket(stateId);
    }
  }

  updateEVAM(stateId: string, evamProcessId: string) {
    if (this.states.has(stateId)) {
      this.states.get(stateId)!.evamProcessId = evamProcessId;
      this.syncSocket(stateId);
    }
  }

  updateDataStoreUploadStatus(stateId: string, status: StateActionStatus) {
    if (this.states.has(stateId)) {
      this.states.get(stateId)!.status.dataStoreUpload = status;
      this.states.get(stateId)!.updatedAt = new Date().toISOString();
      this.syncSocket(stateId);
    }
  }

  private statusSync(stateId: string) {
    this.emitter.emit(SocketEvent.STATUS_SYNC, { stateId });
  }

  updateSummaryStatus(stateId: string, status: StateActionStatus) {
    if (this.states.has(stateId)) {
      this.states.get(stateId)!.status.summarizing = status;

      this.statusSync(stateId);
    }
  }

  addSummaryStream(stateId: string, summaryChunk: string) {
    if (this.states.has(stateId)) {
      this.states.get(stateId)!.summary =
        (this.states.get(stateId)!.summary ?? '') + summaryChunk;
    }
  }

  summaryComplete(stateId: string, summary: string) {
    if (this.states.has(stateId)) {
      this.states.get(stateId)!.summary = summary;
      this.updateSummaryStatus(stateId, StateActionStatus.COMPLETE);
      this.saveToDB(stateId);
      this.emitter.emit(SocketEvent.SUMMARY_SYNC, { stateId, summary });
    }
  }

  updateChunkingStatus(stateId: string, status: StateActionStatus) {
    if (this.states.has(stateId)) {
      this.states.get(stateId)!.status.chunking = status;
      this.statusSync(stateId);
    }
  }

  private frameSummarySync(stateId: string, frameKey: string) {
    this.emitter.emit(SocketEvent.FRAME_SUMMARY_SYNC, { stateId, frameKey });
  }

  addFrameSummary(stateId: string, frameIds: string[], summary: string = '') {
    if (this.states.has(stateId)) {
      const frameIdsNum: number[] = frameIds.map((el) => +el);

      const startFrame = Math.min(...frameIdsNum).toString();
      const endFrame = Math.max(...frameIdsNum).toString();
      const frameKey = frameIds.join('#');

      const frameData = {
        endFrame,
        startFrame,
        frameKey,
        frames: frameIds,
        status: StateActionStatus.READY,
        summary,
      };

      this.states.get(stateId)!.frameSummaries[frameKey] = frameData;
      this.frameSummarySync(stateId, frameKey);
    }
  }

  updateFrameSummary(
    stateId: string,
    frameKey: string,
    status: StateActionStatus,
    summary: string = '',
  ) {
    if (this.states.has(stateId)) {
      if (this.states.get(stateId)!.frameSummaries[frameKey]) {
        this.states.get(stateId)!.frameSummaries[frameKey] = {
          ...this.states.get(stateId)!.frameSummaries[frameKey],
          status,
          summary,
        };
        this.frameSummarySync(stateId, frameKey);
      }
    }
  }

  private configSync(stateId: string) {
    this.emitter.emit(SocketEvent.CONFIG_SYNC, stateId);
  }

  addEVAMInferenceConfig(stateId: string, modelInfo: ModelInfo) {
    if (this.states.has(stateId)) {
      if (!this.states.get(stateId)!.inferenceConfig!.objectDetection) {
        this.states.get(stateId)!.inferenceConfig!.objectDetection = modelInfo;
        this.configSync(stateId);
      }
    }
  }
  addTextInferenceConfig(stateId: string, modelInfo: ModelInfo) {
    if (this.states.has(stateId)) {
      if (!this.states.get(stateId)!.inferenceConfig!.textInference) {
        this.states.get(stateId)!.inferenceConfig!.textInference = modelInfo;
        this.configSync(stateId);
      }
    }
  }
  addImageInferenceConfig(stateId: string, modelInfo: ModelInfo) {
    if (this.states.has(stateId)) {
      if (!this.states.get(stateId)!.inferenceConfig!.imageInference) {
        this.states.get(stateId)!.inferenceConfig!.imageInference = modelInfo;
        this.configSync(stateId);
      }
    }
  }

  searchEmbeddingsCreated(stateId: string, frameKey: string) {
    if (this.states.has(stateId)) {
      if (this.states.get(stateId)!.frameSummaries[frameKey]) {
        this.states.get(stateId)!.frameSummaries[frameKey].embeddingsCreated =
          true;
      }
    }
  }

  async create(
    videoData: Video,
    title: string,
    systemConfig: SystemConfig,
    samplingInputs: SummaryPipelineSampling,
  ) {
    const stateId = uuidV4();
    const state: State = {
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      stateId,
      title,
      video: videoData,
      systemConfig,
      userInputs: samplingInputs,
      chunks: {},
      frames: {},
      frameSummaries: {},
      inferenceConfig: {},
      status: {
        summarizing: StateActionStatus.NA,
        dataStoreUpload: StateActionStatus.NA,
        chunking: StateActionStatus.NA,
      },
    };

    const { video, ...stateWithoutVideo } = state;

    await this.$stateDb.addState({
      ...stateWithoutVideo,
      videoId: video.videoId,
    });

    this.update(state);

    this.emitter.emit(PipelineEvents.SUMMARY_PIPELINE_START, stateId);

    return state;
  }

  async remove(stateId: string) {
    if (this.states.has(stateId)) {
      await this.$stateDb.removeState(stateId);
      this.states.delete(stateId);
      this.emitter.emit(AppEvents.SUMMARY_REMOVED, stateId);
    }
  }

  syncSocket(stateId: string) {
    if (this.states.has(stateId)) {
      this.emitter.emit(SocketEvent.STATE_SYNC, { stateId });
    }
  }
}
