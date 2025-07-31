// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { Injectable } from '@nestjs/common';
import {
  ChunkQueueItem,
  SummaryQueueItem,
} from 'src/evam/models/message-broker.model';
import { LlmService } from 'src/language-model/services/llm.service';
import { StateService } from '../services/state.service';
import { EventEmitter2, OnEvent } from '@nestjs/event-emitter';
import {
  ChunkSummaryComplete,
  ChunkSummaryTrigger,
  PipelineDTOBase,
  PipelineEvents,
  SummaryCompleteRO,
} from 'src/events/Pipeline.events';
import { AppEvents } from 'src/events/app.events';
import { Subject, Subscription } from 'rxjs';
import { TemplateService } from 'src/language-model/services/template.service';
import { ConfigService } from '@nestjs/config';

@Injectable()
export class SummaryService {
  waiting: SummaryQueueItem[] = [];

  processing: SummaryQueueItem[] = [];

  maxConcurrent: number = this.$config.get<number>(
    'openai.llmSummarization.concurrent',
  )!;

  private subs = new Subscription();

  promptingFor = this.$config.get<string>('openai.usecase')! + 'Summary';

  constructor(
    private $config: ConfigService,
    private $state: StateService,
    private $llm: LlmService,
    private $emitter: EventEmitter2,
  ) {}

  @OnEvent(PipelineEvents.SUMMARY_TRIGGER)
  streamTrigger({ stateId }: PipelineDTOBase) {
    this.waiting.push({ stateId });
  }

  startVideoSummary(data: SummaryQueueItem) {
    const { stateId } = data;

    this.$emitter.emit(PipelineEvents.SUMMARY_PROCESSING, { stateId });

    const state = this.$state.fetch(stateId);

    if (state && Object.values(state.frameSummaries).length > 0) {
      const streamer = new Subject<string>();

      let texts = Object.values(state.frameSummaries)
        .sort((a, b) => +a.startFrame - +b.startFrame)
        .map((el) => el.summary);

      const inferenceConfig = this.$llm.getInferenceConfig();

      this.$state.addTextInferenceConfig(stateId, inferenceConfig);

      let mapPrompt = state.systemConfig.summaryMapPrompt;

      if (state.audio && state.audio.transcript.length > 0) {
        const transcripts = state.audio.transcript
          .map((el) =>
            [el.id, `${el.startTime} --> ${el.endTime}`, el.text].join('\n'),
          )
          .join('\n\n');

        if (transcripts) {
          mapPrompt += `Audio transcripts for this video:\n${transcripts}\n\n`;
        }
      }

      this.$llm
        .summarizeMapReduce(
          texts,
          mapPrompt,
          state.systemConfig.summaryReducePrompt,
          state.systemConfig.summarySinglePrompt,
          streamer,
        )
        .catch((error) => {
          console.error('Error summarizing video:', error);
        });

      let summary = '';

      this.subs.add(
        streamer.subscribe({
          next: (res) => {
            summary += res;
            this.$emitter.emit(PipelineEvents.SUMMARY_STREAM, {
              stateId,
              streamChunk: res,
            });
          },
          complete: () => {
            console.log('SUMMARY COMPLETE', summary);
            this.$emitter.emit(PipelineEvents.SUMMARY_COMPLETE, {
              stateId,
              summary,
            });
          },
        }),
      );
    }
  }

  @OnEvent(AppEvents.TICK)
  processQueue() {
    if (this.processing.length < this.maxConcurrent) {
      const queueItem = this.waiting.shift();

      if (queueItem) {
        this.processing.push(queueItem);
        this.startVideoSummary(queueItem);
      }
    }
  }

  @OnEvent(PipelineEvents.SUMMARY_COMPLETE)
  summaryComplete({ stateId, summary }: SummaryCompleteRO) {
    const processingIndex = this.processing.findIndex(
      (el) => el.stateId == stateId,
    );

    if (processingIndex > -1) {
      this.processing.splice(processingIndex, 1);
    }
  }
}
