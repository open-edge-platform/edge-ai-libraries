// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { Injectable } from '@nestjs/common';
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
import { TemplateService } from 'src/language-model/services/template.service';
import { ConfigService } from '@nestjs/config';

import * as srtParserLib from 'srt-parser-2';
import { Span, TraceService } from 'nestjs-otel';

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
    private $template: TemplateService,
    private $trace: TraceService,
  ) {}

  @OnEvent(PipelineEvents.CHUNKING_COMPLETE)
  prepareFrames(stateIds: string[]) {
    console.log(stateIds);
    const currentSpan = this.$trace.getSpan();
    const tracer = this.$trace.getTracer();

    let spanContext: { context: any } | null = null;
    if (currentSpan) {
      spanContext = { context: currentSpan.spanContext() };
    }

    for (const stateId of stateIds) {
      const subSpan = tracer.startSpan(
        `ChunkingService.prepareFrames.workload.${stateId}`,
        {
          links: currentSpan && spanContext ? [spanContext] : [],
        },
      );

      subSpan.setAttribute('stateId', stateId);

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

        subSpan.addEvent('Creating chunking workload', {
          multiFrame: state.systemConfig.multiFrame,
          overlap: state.systemConfig.frameOverlap,
          samplingFrame: state.userInputs.samplingFrame,
        });

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

          subSpan.addEvent('Adding chunk to queue', {
            left: actualLeft,
            right: windowRight,
            frames: relevantFrames.map((el) => el.frameId),
          });

          this.addChunk(
            stateId,
            relevantFrames.map((el) => el.frameId),
          );

          windowLeft += windowLength;
          actualLeft = windowLeft;

          if (actualLeft < 0) {
            actualLeft = 0;
          }

          windowRight += windowLength;

          if (windowRight > frames.length) {
            windowRight = frames.length;
          }
        }
      }
      subSpan.end();
    }
  }

  addChunk(stateId: string, frames: string[]) {
    const queueKey: string = frames.join('#');
    this.waiting.push({ stateId, frames, queueKey });
    this.$state.addFrameSummary(stateId, frames);
  }

  @OnEvent(AppEvents.TICK)
  checkProcessing() {
    if (
      this.processing.length < this.maxConcurrent &&
      this.waiting.length > 0 &&
      this.$vlm.serviceReady
    ) {
      const nextFrame = this.waiting.shift();

      if (nextFrame) {
        this.processing.push(nextFrame);

        const tracer = this.$trace.getTracer();

        const { stateId, frames } = nextFrame;

        const state = this.$state.fetch(stateId);

        if (state) {
          const chunkSpan = tracer.startSpan('CHUNK_OVERVIEW', {
            attributes: { stateId, videoId: state.video.videoId },
          });

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

              chunkSpan.addEvent('Preparing VLM inference', {
                stateId,
                frameCount: queryData.length,
              });

              const vlmInference = this.$vlm.getInferenceConfig();
              this.$state.addImageInferenceConfig(stateId, vlmInference);

              chunkSpan.setAttribute(
                'vlm.inferenceConfig',
                JSON.stringify(vlmInference),
              );

              if (state.audio && state.audio.transcript.length > 0) {
                const chunkDuration = state.userInputs.chunkDuration;
                const sampleFrames = +state.userInputs.samplingFrame;

                const sortedFrames = nextFrame.frames.sort((a, b) => +a - +b);

                const firstFrame: number = +sortedFrames[0];
                const lastFrame: number =
                  +sortedFrames[sortedFrames.length - 1];

                const startChunk = Math.floor(firstFrame / sampleFrames);
                const endChunk = Math.floor(lastFrame / sampleFrames);

                const startTime =
                  startChunk * chunkDuration +
                  (chunkDuration * firstFrame) / sampleFrames;
                const endTime =
                  endChunk * chunkDuration +
                  (chunkDuration * lastFrame) / sampleFrames;

                transcripts = state.audio.transcript
                  .filter(
                    (el) =>
                      (el.startSeconds >= startTime &&
                        el.startSeconds <= endTime) ||
                      (el.endSeconds >= startTime && el.endSeconds <= endTime),
                  )
                  .map((el) =>
                    [el.id, `${el.startTime} --> ${el.endTime}`, el.text].join(
                      '\n',
                    ),
                  )
                  .join('\n\n');
                chunkSpan.addEvent('Transcripts prepared', {
                  transcriptsCount: state.audio.transcript.length,
                  transcripts: transcripts.length,
                });
              }

              let prompt = state.systemConfig.framePrompt;

              // Process Detected Objects
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

              if (detectedObjects.size > 0) {
                prompt = this.$template.addDetectedObjects(
                  prompt,
                  detectedObjects,
                );
              }

              if (transcripts) {
                prompt = this.$template.addAudioTranscript(prompt, transcripts);
              }

              console.log('Prompting for:', nextFrame.queueKey, prompt);

              chunkSpan.addEvent('Prompting for VLM inference', {
                stateId,
                queueKey: nextFrame.queueKey,
                prompt,
              });

              this.subs.add(
                from(
                  this.$vlm.imageInference(
                    prompt,
                    queryData.map((el) => el.imageUrl),
                  ),
                ).subscribe({
                  next: (res: string | null) => {
                    if (res) {
                      console.log('Response from VLM: ', res);

                      chunkSpan.addEvent('VLM inference complete', {
                        stateId,
                        queueKey: nextFrame.queueKey,
                        responseLength: res.length,
                      });

                      chunkSpan.end();

                      this.$emitter.emit(
                        PipelineEvents.FRAME_CAPTION_COMPLETE,
                        {
                          stateId,
                          frameIds: queryData.map((el) => el.frameData.frameId),
                          caption: res,
                        },
                      );
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

  public hasProcessing(stateId: string): boolean {
    return (
      this.waiting.some((el) => el.stateId === stateId) ||
      this.processing.some((el) => el.stateId === stateId)
    );
  }

  @OnEvent(PipelineEvents.FRAME_CAPTION_COMPLETE)
  frameCaptionComplete({ stateId, caption, frameIds }: FrameCaptionEventDTO) {
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
