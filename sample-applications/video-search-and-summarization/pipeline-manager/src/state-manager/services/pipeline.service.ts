// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Injectable } from '@nestjs/common';
import { StateService } from './state.service';
import { DatastoreService } from 'src/datastore/services/datastore.service';
import { EventEmitter2, OnEvent } from '@nestjs/event-emitter';
import {
  FrameCaptionEventDTO,
  PipelineDTOBase,
  PipelineEvents,
  PipelineUploadToDS,
  SummaryCompleteRO,
  SummaryStreamChunk,
} from 'src/events/Pipeline.events';
import { ChunkQueue } from 'src/evam/models/message-broker.model';
import { EvamService } from 'src/evam/services/evam.service';
import { lastValueFrom } from 'rxjs';
import { ChunkingService } from 'src/state-manager/queues/chunking.service';
import { StateActionStatus } from '../models/state.model';

import { LocalstoreService } from 'src/datastore/services/localstore.service';
import { unlinkSync } from 'fs';
import { AudioQueueService } from '../queues/audio-queue.service';
import { AudioService } from 'src/audio/services/audio.service';
import { VlmService } from 'src/language-model/services/vlm.service';
import { LlmService } from 'src/language-model/services/llm.service';

@Injectable()
export class PipelineService {
  constructor(
    private $state: StateService,
    private $dataStore: DatastoreService,
    private $localStore: LocalstoreService,
    private $event: EventEmitter2,
    private $evam: EvamService,
    private $audio: AudioService,
    private $chunking: ChunkingService,
    private $audioQueue: AudioQueueService,
    private $vlm: VlmService,
    private $llm: LlmService,
  ) {}

  @OnEvent(PipelineEvents.CHUNKING_COMPLETE)
  async chunkingComplete(states: string[]) {
    for (const stateId of states) {
      this.$state.updateChunkingStatus(stateId, StateActionStatus.COMPLETE);
    }
  }

  @OnEvent(PipelineEvents.CHECK_QUEUE_STATUS)
  async checkQueueStatus(stateId: string[]) {
    const notInProgress: string[] = stateId.reduce(
      (acc: string[], stateId: string) => {
        const evamInProgress = this.$evam.isChunkingInProgress(stateId);
        const audioInProgress = this.$audioQueue.isAudioProcessing(stateId);

        // Mark video chunking complete independently of audio
        if (!evamInProgress) {
          this.$state.updateVideoChunkingStatus(stateId, StateActionStatus.COMPLETE);
        }

        if (!evamInProgress && !audioInProgress) {
          acc.push(stateId);
        }

        return acc;
      },
      [],
    );

    if (notInProgress.length > 0) {
      this.$event.emit(PipelineEvents.CHUNKING_COMPLETE, notInProgress);
    }
  }

  // @OnEvent(PipelineEvents.UPLOAD_TO_DATASTORE)
  // async startPipeline(payload: PipelineUploadToDS) {
  //   const state = this.$state.fetch(payload.stateId);
  //   if (state) {
  //     this.$state.updateDataStoreUploadStatus(
  //       payload.stateId,
  //       StateActionStatus.IN_PROGRESS,
  //     );

  //     try {
  //       const { stateId, fileInfo } = payload;

  //       const { objectPath, fileExtn } = this.$dataStore.getObjectName(
  //         stateId,
  //         fileInfo.originalname,
  //       );

  //       const res = await this.$dataStore.uploadFile(objectPath, fileInfo.path);
  //       console.log('uploaded to datastore', res);

  //       this.$state.updateDataStoreUploadStatus(
  //         stateId,
  //         StateActionStatus.COMPLETE,
  //       );

  //       this.$event.emit(PipelineEvents.UPLOAD_TO_DATASTORE_COMPLETE, stateId);
  //       this.$state.updateChunkingStatus(stateId, StateActionStatus.READY);
  //     } catch (error) {
  //       console.log(PipelineEvents.UPLOAD_TO_DATASTORE, 'ERROR', error);
  //     }
  //   }
  // }

  @OnEvent(PipelineEvents.CHUNKING_TRIGGERED)
  chunkingTriggered({ stateId }: { stateId: string }) {
    this.$state.updateChunkingStatus(stateId, StateActionStatus.IN_PROGRESS);
    this.$state.updateVideoChunkingStatus(stateId, StateActionStatus.IN_PROGRESS);
  }

  @OnEvent(PipelineEvents.SUMMARY_PIPELINE_START)
  async triggerChunking(stateId: string) {
    const state = this.$state.fetch(stateId);

    if (state && state.video.dataStore) {
      try {
        const videoUrl = this.$dataStore.getObjectURL(state.video.url);

        this.$event.emit(PipelineEvents.CHUNKING_TRIGGERED, { stateId });
        if (state.systemConfig.audioModel) {
          this.$event.emit(PipelineEvents.AUDIO_TRIGGERED, stateId);
        }
        const res = await lastValueFrom(
          this.$evam.startChunkingStub(
            stateId,
            videoUrl,
            state.userInputs,
            state.systemConfig.evamPipeline,
          ),
        );

        this.$state.addEVAMInferenceConfig(
          stateId,
          this.$evam.getInferenceConfig(),
        );

        // Pre-populate VLM and LLM inference configs so UI shows model info upfront
        if (this.$vlm.serviceReady) {
          this.$state.addImageInferenceConfig(
            stateId,
            this.$vlm.getInferenceConfig(),
          );
        }
        if (this.$llm.serviceReady) {
          this.$state.addTextInferenceConfig(
            stateId,
            this.$llm.getInferenceConfig(),
          );
        }

        if (res.data) {
          console.log(res.data);
          this.$evam.addStateToProgress(stateId, res.data);
          this.$state.updateEVAM(stateId, res.data);
        }
      } catch (error) {
        console.log('ERROR MESSAGE', error.message);
        console.log('ERROR REQUEST', error.request);
      }
    }
  }

  @OnEvent(PipelineEvents.CHUNK_RECEIVED)
  async triggerChunkCaptioning(chunkData: ChunkQueue) {
    const stateId = chunkData.evamIdentifier;
    this.$state.addChunk(stateId, chunkData);
  }

  @OnEvent(PipelineEvents.FRAME_CAPTION_PROCESSING)
  frameCaptionProgress(payload: FrameCaptionEventDTO) {
    const { stateId, frameIds } = payload;

    const frameKey = frameIds.join('#');

    this.$state.updateFrameSummary(
      stateId,
      frameKey,
      StateActionStatus.IN_PROGRESS,
    );
  }

  @OnEvent(PipelineEvents.FRAME_CAPTION_COMPLETE)
  updateFrameCaption(payload: FrameCaptionEventDTO) {
    const { caption, stateId, frameIds } = payload;
    const frameKey = frameIds.join('#');
    this.$state.updateFrameSummary(
      stateId,
      frameKey,
      StateActionStatus.COMPLETE,
      caption,
    );

    // const anyIncomplete = this.$chunking.hasProcessing(stateId);
    // console.log(`anyIncomplete:${anyIncomplete}`)

    // if (!anyIncomplete) {
    //   this.$event.emit(PipelineEvents.SUMMARY_TRIGGER, { stateId });
    // }
  }

  @OnEvent(PipelineEvents.SUMMARY_TRIGGER)
  summaryTrigger({ stateId }: PipelineDTOBase) {
    this.$state.updateSummaryStatus(stateId, StateActionStatus.READY);
  }

  @OnEvent(PipelineEvents.SUMMARY_PROCESSING)
  summaryProcessing({ stateId }: PipelineDTOBase) {
    this.$state.updateSummaryStatus(stateId, StateActionStatus.IN_PROGRESS);
  }

  @OnEvent(PipelineEvents.SUMMARY_STREAM)
  summaryStream({ stateId, streamChunk }: SummaryStreamChunk) {
    this.$state.addSummaryStream(stateId, streamChunk);
  }

  @OnEvent(PipelineEvents.SUMMARY_COMPLETE)
  summaryComplete({ stateId, summary }: SummaryCompleteRO) {
    console.log(' SUMMARY COMPLETE PIPELINE', stateId, summary);
    this.$state.summaryComplete(stateId, summary);
  }
}
