// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Injectable } from '@nestjs/common';
import { SummaryQueueItem } from 'src/evam/models/message-broker.model';
import { LlmService } from 'src/language-model/services/llm.service';
import { StateService } from '../services/state.service';
import { EventEmitter2, OnEvent } from '@nestjs/event-emitter';
import {
  PipelineDTOBase,
  PipelineEvents,
  SummaryCompleteRO,
} from 'src/events/Pipeline.events';
import { AppEvents } from 'src/events/app.events';
import { Subject, Subscription } from 'rxjs';
import { ConfigService } from '@nestjs/config';
import { InferenceCountService } from 'src/language-model/services/inference-count.service';
import { State, StateActionStatus } from '../models/state.model';
import { TemplateService } from 'src/language-model/services/template.service';

@Injectable()
export class SummaryQueueService {
  waiting: SummaryQueueItem[] = [];
  processing: SummaryQueueItem[] = [];

  private subs = new Subscription();

  promptingFor = this.$config.get<string>('openai.usecase')! + 'Summary';

  constructor(
    private $config: ConfigService,
    private $state: StateService,
    private $llm: LlmService,
    private $template: TemplateService,
    private $emitter: EventEmitter2,
    private $inferenceCount: InferenceCountService,
  ) {}

  @OnEvent(PipelineEvents.SUMMARY_TRIGGER)
  streamTrigger({ stateId }: PipelineDTOBase) {
    const state = this.$state.fetch(stateId);

    const alreadyQueued =
      this.waiting.some(
        (el) =>
          el.stateId === stateId && el.taskType === 'videoSummary',
      ) ||
      this.processing.some(
        (el) =>
          el.stateId === stateId && el.taskType === 'videoSummary',
      );

    if (
      alreadyQueued ||
      state?.status.summarizing === StateActionStatus.IN_PROGRESS ||
      state?.status.summarizing === StateActionStatus.COMPLETE
    ) {
      return;
    }

    this.waiting.push({ stateId, taskType: 'videoSummary' });
  }

  @OnEvent(PipelineEvents.AUDIO_SUMMARY_TRIGGER)
  audioSummaryTrigger({ stateId }: PipelineDTOBase) {
    const alreadyQueued =
      this.waiting.some(
        (item) =>
          item.stateId === stateId &&
          item.taskType === 'audioTranscriptSummary',
      ) ||
      this.processing.some(
        (item) =>
          item.stateId === stateId &&
          item.taskType === 'audioTranscriptSummary',
      );

    if (!alreadyQueued) {
      this.waiting.unshift({ stateId, taskType: 'audioTranscriptSummary' });
    }
  }

  startVideoSummary(data: SummaryQueueItem) {
    this.$inferenceCount.incrementLlmProcessCount();
    const { stateId } = data;

    this.$emitter.emit(PipelineEvents.SUMMARY_PROCESSING, { stateId });

    const state = this.$state.fetch(stateId);

    if (!state || Object.values(state.frameSummaries).length === 0) {
      this.$inferenceCount.decrementLlmProcessCount();
      this.removeProcessingItem(stateId, 'videoSummary');
      return;
    }

    if (state && Object.values(state.frameSummaries).length > 0) {
      const streamer = new Subject<string>();

      const texts = Object.values(state.frameSummaries)
        .sort((a, b) => +a.startFrame - +b.startFrame)
        .map((el) => el.summary);

      const inferenceConfig = this.$llm.getInferenceConfig();

      this.$state.addTextInferenceConfig(stateId, inferenceConfig);

      let mapPrompt = state.systemConfig.summaryMapPrompt;

      const useAudioTranscriptSummary =
        this.shouldUseAudioTranscriptSummary(state);

      if (useAudioTranscriptSummary) {
        const audioSummary = state.audio?.transcriptSummary ?? '';
        const audioBlock = `\nThe following is a summary of the video's spoken audio. Integrate relevant dialogue, narration, or spoken context naturally with the visual observations.\n\nAudio Transcript Summary:\n${audioSummary}\n`;
        mapPrompt = mapPrompt.replaceAll('%audio_summary%', audioBlock);
      } else {
        mapPrompt = mapPrompt.replaceAll('%audio_summary%', '');
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
          this.$inferenceCount.decrementLlmProcessCount();
          this.removeProcessingItem(stateId, 'videoSummary');
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
          error: () => {
            this.$inferenceCount.decrementLlmProcessCount();
            this.removeProcessingItem(stateId, 'videoSummary');
          },
        }),
      );
    }
  }

  startAudioTranscriptSummary(data: SummaryQueueItem) {
    this.$inferenceCount.incrementLlmProcessCount();

    const { stateId } = data;
    const state = this.$state.fetch(stateId);

    if (!state || !state.audio || state.audio.transcript.length === 0) {
      this.$emitter.emit(PipelineEvents.AUDIO_SUMMARY_COMPLETE, { stateId });
      return;
    }

    this.$state.audioTranscriptSummaryProcessing(stateId);

    const transcripts = state.audio.transcript
      .map((el) =>
        [el.id, `${el.startTime} --> ${el.endTime}`, el.text].join('\n'),
      )
      .join('\n\n');

    const streamer = new Subject<string>();
    let audioSummary = '';

    const { mapPrompt, reducePrompt, singlePrompt } =
      this.getAudioTranscriptPrompts(state);

    this.$llm
      .summarizeMapReduce(
        [transcripts],
        mapPrompt,
        reducePrompt,
        singlePrompt,
        streamer,
      )
      .catch((error) => {
        this.$inferenceCount.decrementLlmProcessCount();
        this.removeProcessingItem(stateId, 'audioTranscriptSummary');
        console.error('Error summarizing transcript:', error);
      });

    this.subs.add(
      streamer.subscribe({
        next: (res) => {
          audioSummary += res;
        },
        complete: () => {
          this.$state.audioTranscriptSummaryComplete(stateId, audioSummary);
          this.$emitter.emit(PipelineEvents.AUDIO_SUMMARY_COMPLETE, {
            stateId,
          });
        },
        error: () => {
          this.$inferenceCount.decrementLlmProcessCount();
          this.removeProcessingItem(stateId, 'audioTranscriptSummary');
        },
      }),
    );
  }

  @OnEvent(AppEvents.SUMMARY_REMOVED)
  removeSummary(stateId: string) {
    this.waiting = this.waiting.filter((el) => el.stateId !== stateId);
    this.processing = this.processing.filter((el) => el.stateId !== stateId);
  }

  @OnEvent(AppEvents.FAST_TICK)
  processQueue() {
    if (this.waiting.length > 0 && this.$inferenceCount.hasLlmSlots()) {
      const nextReadyIndex = this.waiting.findIndex((item) =>
        this.isQueueItemReady(item),
      );

      if (nextReadyIndex > -1) {
        const queueItem = this.waiting.splice(nextReadyIndex, 1)[0];
        this.processing.push(queueItem);

        if (queueItem.taskType === 'audioTranscriptSummary') {
          this.startAudioTranscriptSummary(queueItem);
        } else {
          this.startVideoSummary(queueItem);
        }
      }
    }
  }

  @OnEvent(PipelineEvents.SUMMARY_COMPLETE)
  summaryComplete({ stateId }: SummaryCompleteRO) {
    this.removeProcessingItem(stateId, 'videoSummary');
    this.$inferenceCount.decrementLlmProcessCount();
  }

  @OnEvent(PipelineEvents.AUDIO_SUMMARY_COMPLETE)
  audioSummaryComplete({ stateId }: PipelineDTOBase) {
    this.removeProcessingItem(stateId, 'audioTranscriptSummary');
    this.$inferenceCount.decrementLlmProcessCount();
  }

  private removeProcessingItem(
    stateId: string,
    taskType: 'videoSummary' | 'audioTranscriptSummary',
  ) {
    const processingIndex = this.processing.findIndex(
      (el) => el.stateId === stateId && el.taskType === taskType,
    );

    if (processingIndex > -1) {
      this.processing.splice(processingIndex, 1);
    }
  }

  private shouldUseAudioTranscriptSummary(state: State): boolean {
    return Boolean(
      state.systemConfig.audioModel &&
        state.systemConfig.audioUseFullTranscriptSummary,
    );
  }

  private isQueueItemReady(item: SummaryQueueItem): boolean {
    const state = this.$state.fetch(item.stateId);

    if (!state) {
      return false;
    }

    if (item.taskType === 'audioTranscriptSummary') {
      return Boolean(state.audio && state.audio.transcript.length > 0);
    }

    if (!this.shouldUseAudioTranscriptSummary(state)) {
      return true;
    }

    return (
      state.audio?.transcriptSummaryStatus === StateActionStatus.COMPLETE &&
      Boolean(state.audio?.transcriptSummary)
    );
  }

  private getAudioTranscriptPrompts(state: State): {
    mapPrompt: string;
    reducePrompt: string;
    singlePrompt: string;
  } {
    const useCase = this.$config.get<string>('openai.usecase') ?? 'default';

    const mapPrompt =
      state.systemConfig.audioSummaryMapPrompt ||
      this.$template.getTemplate(`${useCase}AudioSummary`) ||
      this.$template.getTemplate('defaultAudioSummary') ||
      state.systemConfig.summaryMapPrompt;

    const reducePrompt =
      state.systemConfig.audioSummaryReducePrompt ||
      this.$template.getTemplate(`${useCase}AudioReduce`) ||
      this.$template.getTemplate('defaultAudioReduce') ||
      state.systemConfig.summaryReducePrompt;

    const singlePrompt =
      state.systemConfig.audioSummarySinglePrompt ||
      this.$template.getTemplate(`${useCase}AudioSingle`) ||
      this.$template.getTemplate('defaultAudioSingle') ||
      state.systemConfig.summarySinglePrompt;

    return { mapPrompt, reducePrompt, singlePrompt };
  }
}
