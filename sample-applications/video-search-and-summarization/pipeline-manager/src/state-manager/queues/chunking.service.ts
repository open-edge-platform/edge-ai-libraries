// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Injectable, Logger } from '@nestjs/common';
import { EventEmitter2, OnEvent } from '@nestjs/event-emitter';
import { FrameQueueItem } from 'src/evam/models/message-broker.model';
import { AppEvents } from 'src/events/app.events';
import {
  FrameCaptionEventDTO,
  PipelineEvents,
} from 'src/events/Pipeline.events';
import { StateService } from 'src/state-manager/services/state.service';
import { VlmService } from '../../language-model/services/vlm.service';
import { from, Subscription } from 'rxjs';
import { DatastoreService } from 'src/datastore/services/datastore.service';
import { ConfigService } from '@nestjs/config';

import { FeaturesEnum, FeaturesService } from 'src/features/features.service';
import { InferenceCountService } from 'src/language-model/services/inference-count.service';
import { State, StateChunkFrame } from '../models/state.model';
import { TemplateService } from 'src/language-model/services/template.service';
import { DataPrepShimService } from 'src/data-prep/services/data-prep-shim.service';
import { DataPrepSummaryDTO } from 'src/data-prep/models/data-prep.models';

@Injectable()
export class ChunkingService {
  waiting: FrameQueueItem[] = [];

  processing: FrameQueueItem[] = [];

  maxConcurrent: number = this.$config.get<number>(
    'openai.vlmCaptioning.concurrent',
  )!;

  promptingFor = this.$config.get<string>('openai.usecase')! + 'Frames';

  subs = new Subscription();

  constructor(
    private $config: ConfigService,
    private $state: StateService,
    private $vlm: VlmService,
    private $emitter: EventEmitter2,
    private $dataStore: DatastoreService,
    private $searchDataPrep: DataPrepShimService,
    private $feature: FeaturesService,
    private $inferenceCount: InferenceCountService,
    private $template: TemplateService,
  ) {}

  @OnEvent(PipelineEvents.CHUNKING_COMPLETE)
  prepareFrames(stateIds: string[]) {
    console.log(stateIds);

    for (const stateId of stateIds) {
      const state = this.$state.fetch(stateId);

      if (state) {
        console.log(state);

        const frames = (Object.values(state.frames) ?? []).sort(
          (a, b) => +a.frameId - +b.frameId,
        );

        console.log(
          'FRAMES',
          frames.map((el) => el.frameId),
        );

        console.log('MULTI', state.systemConfig.multiFrame);
        console.log('OVERLAP', state.systemConfig.frameOverlap);
        console.log('samplingFrame', state.userInputs.samplingFrame);

        const { multiFrame, frameOverlap } = state.systemConfig;
        const samplingFrame = state.userInputs.samplingFrame;

        let windowLeft = 0;
        let actualLeft = 0;
        const windowLength = multiFrame - frameOverlap;
        let windowRight = windowLeft + Math.min(multiFrame, samplingFrame);

        while (windowLeft < frames.length) {
          const relevantFrames = frames.slice(actualLeft, windowRight);
          console.log(
            'REL',
            actualLeft,
            windowLeft,
            windowRight,
            relevantFrames.map((el) => el.frameId),
          );
          this.addChunk(
            stateId,
            relevantFrames.map((el) => el.frameId),
          );

          windowLeft += windowLength;
          actualLeft = windowLeft - frameOverlap;

          if (actualLeft < 0) {
            actualLeft = 0;
          }

          windowRight += windowLength;

          if (windowRight > frames.length) {
            windowRight = frames.length;
          }
        }
      }
    }
  }

  addChunk(stateId: string, frames: string[]) {
    const queueKey: string = frames.join('#');
    this.waiting.push({ stateId, frames, queueKey });
    this.$state.addFrameSummary(stateId, frames);
  }

  @OnEvent(AppEvents.SUMMARY_REMOVED)
  removeChunking(stateId: string) {
    this.waiting = this.waiting.filter((el) => el.stateId !== stateId);
    this.processing = this.processing.filter((el) => el.stateId !== stateId);
  }

  @OnEvent(AppEvents.TICK)
  checkProcessing() {
    if (
      this.waiting.length > 0 &&
      this.$inferenceCount.hasVlmSlots() &&
      this.$vlm.serviceReady
    ) {
      const nextFrame = this.waiting.shift();

      if (nextFrame) {
        this.processing.push(nextFrame);

        const { stateId, frames } = nextFrame;

        const state = this.$state.fetch(stateId);

        if (state) {
          this.$emitter.emit(PipelineEvents.FRAME_CAPTION_PROCESSING, {
            stateId,
            frameIds: frames,
          });

          const framesData = frames
            .map((frameId: string) => this.$state.fetchFrame(stateId, frameId))
            .filter((el) => el);

          if (framesData.length > 0) {
            const queryData = framesData.map((frameData) => {
              return {
                frameData: frameData!,
                query: '',
                imageUrl: this.$dataStore.getWithURL(frameData!.frameUri),
              };
            });

            let transcripts: string = '';

            if (queryData.length > 0) {
              this.$emitter.emit(PipelineEvents.FRAME_CAPTION_PROCESSING, {
                stateId,
                frameIds: queryData.map((data) => data.frameData.frameId),
                caption: '',
              });

              const vlmInference = this.$vlm.getInferenceConfig();
              this.$state.addImageInferenceConfig(stateId, vlmInference);

              let prompt = state.systemConfig.framePrompt;

              // Process Detected Objects
              const detectedObjects = this.extractDetectedObjects(
                nextFrame,
                stateId,
              );

              if (detectedObjects.size > 0) {
                prompt = this.$template.addDetectedObjects(
                  prompt,
                  detectedObjects,
                );
              }

              // Process Audio Transcripts
              transcripts = this.getAudioTranscripts(
                state,
                nextFrame,
                transcripts,
              );
              if (transcripts) {
                prompt = this.$template.addAudioTranscripts(
                  prompt,
                  transcripts,
                );
              }

              console.log('Prompting for:', nextFrame.queueKey, prompt);

              this.subs.add(
                from(
                  this.$vlm.imageInference(
                    prompt,
                    queryData.map((el) => el.imageUrl),
                  ),
                ).subscribe({
                  next: (res: string | null) => {
                    if (res) {
                      this.inferenceCompleteHandler(res, stateId, queryData);
                    }
                  },
                  error: (err) => {
                    console.log('Inference error', err);
                  },
                }),
              );
            }
          }
        }
      }
    }
  }

  private extractDetectedObjects(nextFrame: FrameQueueItem, stateId: string) {
    const detectedObjects = new Set<string>();

    for (const frame of nextFrame.frames) {
      const frameData = this.$state.fetchFrame(stateId, frame);
      if (
        frameData &&
        frameData.metadata &&
        frameData.metadata.objects &&
        frameData.metadata.objects.length > 0
      ) {
        frameData.metadata.objects.forEach((obj) => {
          if (obj.detection && obj.detection.label) {
            detectedObjects.add(obj.detection.label);
          }
        });
      }
    }
    return detectedObjects;
  }

  private inferenceCompleteHandler(
    res: string,
    stateId: string,
    queryData: {
      frameData: StateChunkFrame;
      query: string;
      imageUrl: string;
    }[],
  ) {
    console.log('Response from VLM: ', res);

    const payload = {
      stateId,
      frameIds: queryData.map((el) => el.frameData.frameId),
      caption: res,
    };

    if (this.$feature.hasFeature(FeaturesEnum.SEARCH)) {
      this.$emitter.emit(PipelineEvents.CHUNK_SEARCH_EMBEDDINGS, payload);
    }
    this.$emitter.emit(PipelineEvents.FRAME_CAPTION_COMPLETE, payload);
  }

  private getAudioTranscripts(
    state: State,
    nextFrame: FrameQueueItem,
    transcripts: string,
  ) {
    if (state.audio && state.audio.transcript.length > 0) {
      const chunkDuration = state.userInputs.chunkDuration;
      const sampleFrames = +state.userInputs.samplingFrame;

      const sortedFrames = nextFrame.frames.sort((a, b) => +a - +b);

      const firstFrame: number = +sortedFrames[0];
      const lastFrame: number = +sortedFrames[sortedFrames.length - 1];

      const startChunk = Math.floor(firstFrame / sampleFrames);
      const endChunk = Math.floor(lastFrame / sampleFrames);

      const startTime =
        startChunk * chunkDuration +
        (chunkDuration * firstFrame) / sampleFrames;
      const endTime =
        endChunk * chunkDuration + (chunkDuration * lastFrame) / sampleFrames;

      console.log('IN AUDIO:', startTime, endTime);

      transcripts = state.audio.transcript
        .filter(
          (el) =>
            (el.startSeconds >= startTime && el.startSeconds <= endTime) ||
            (el.endSeconds >= startTime && el.endSeconds <= endTime),
        )
        .map((el) =>
          [el.id, `${el.startTime} --> ${el.endTime}`, el.text].join('\n'),
        )
        .join('\n\n');
    }
    return transcripts;
  }

  public hasProcessing(stateId: string): boolean {
    return (
      this.waiting.some((el) => el.stateId === stateId) ||
      this.processing.some((el) => el.stateId === stateId)
    );
  }

  @OnEvent(PipelineEvents.CHUNK_SEARCH_EMBEDDINGS)
  createChunkSearchEmbeddings(data: FrameCaptionEventDTO) {
    const { stateId, frameIds, caption } = data;

    const state = this.$state.fetch(stateId);
    if (state) {
      const chunkDuration = state.userInputs.chunkDuration;

      const firstFrameId = frameIds[0];
      const lastFrameId = frameIds[frameIds.length - 1];

      const midFrameId: number = Math.floor((+lastFrameId + +firstFrameId) / 2);

      const midFrame = state.frames[midFrameId];
      if (!midFrame) {
        Logger.error(
          `Frame with ID ${midFrameId} not found in state ${stateId}`,
        );
        return;
      }

      const chunkStartTime = +midFrame.chunkId * chunkDuration;
      const chunkEndTime = chunkStartTime + chunkDuration;

      const embeddingDTO: DataPrepSummaryDTO = {
        bucket_name: this.$dataStore.bucket,
        video_id: state.video.videoId,
        video_summary: caption,
        video_start_time: chunkStartTime,
        video_end_time: chunkEndTime,
        tags: state.video.tags,
      };

      this.$searchDataPrep.createEmbeddingsFromSummary(embeddingDTO).subscribe({
        next: () => {
          Logger.log(
            'Search embeddings created for chunk',
            stateId,
            frameIds,
            caption,
          );
          this.$state.searchEmbeddingsCreated(stateId, frameIds.join('#'));
        },
        error: (error: any) => {
          Logger.error(
            'Error creating search embeddings for chunk',
            stateId,
            frameIds,
            error,
          );
        },
      });
    }
  }

  @OnEvent(PipelineEvents.FRAME_CAPTION_COMPLETE)
  frameCaptionComplete(data: FrameCaptionEventDTO) {
    const { stateId, frameIds } = data;
    const queueKey = frameIds.join('#');

    const processingIndex = this.processing.findIndex(
      (el) => el.stateId == stateId && queueKey === queueKey,
    );

    if (processingIndex > -1) {
      console.log('Processing Complete', stateId, queueKey, frameIds);
      this.processing.splice(processingIndex, 1);
    }
    const anyIncomplete = this.hasProcessing(stateId);
    console.log(`anyIncomplete:${anyIncomplete}`);

    if (!anyIncomplete) {
      this.$emitter.emit(PipelineEvents.SUMMARY_TRIGGER, { stateId });
    }
  }
}
