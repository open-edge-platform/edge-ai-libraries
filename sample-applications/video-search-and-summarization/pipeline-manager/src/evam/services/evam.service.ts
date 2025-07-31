// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { HttpService } from '@nestjs/axios';
import { Injectable } from '@nestjs/common';
import {
  ChunkingRequestDTO,
  EvamPipelineOption,
  EVAMPipelineRO,
  EVAMPipelines,
} from '../models/evam.model';
import { ConfigService } from '@nestjs/config';

import { DateTime } from 'luxon';
import { EventEmitter2, OnEvent } from '@nestjs/event-emitter';
import { AppEvents } from 'src/events/app.events';
import { lastValueFrom } from 'rxjs';
import { AxiosResponse } from 'axios';
import { PipelineEvents } from 'src/events/Pipeline.events';
import { ModelInfo } from 'src/state-manager/models/state.model';
import { SummaryPipelineSampling } from 'src/summary/models/summary-pipeline.model';

export interface ChunkingProgress {
  stateId: string;
  pipelineId: string;
}

@Injectable()
export class EvamService {
  private host: string = this.$config.get('evam.host')!;
  private pipelinePort: number =
    +this.$config.get<number>('evam.pipelinePort')!;
  private publishPort: number = +this.$config.get<number>('evam.publishPort')!;
  private videoTopic: string = this.$config.get('evam.videoTopic')!;

  inProgress: Map<string, ChunkingProgress> = new Map<
    string,
    ChunkingProgress
  >();

  private checkingStatus = false;

  constructor(
    private $http: HttpService,
    private $config: ConfigService,
    private $emitter: EventEmitter2,
  ) {}

  getVideoTimeStamp(): string {
    const format: string = this.$config.get('evam.datetimeFormat')!;
    return DateTime.now().toFormat(format);
  }

  async getPipelineStatus(pipelineId: string) {
    const api = `http://${this.host}:${this.pipelinePort}/pipelines/${pipelineId}`;
    return lastValueFrom(this.$http.get<EVAMPipelineRO>(api));
  }

  @OnEvent(AppEvents.TICK)
  async checkChunkingStatus() {
    try {
      // console.log(this.chunkingStatus);

      // console.log(this.inProgress);

      if (!this.checkingStatus) {
        this.checkingStatus = true;

        const statusPromises: Promise<AxiosResponse<EVAMPipelineRO, any>>[] =
          [];

        this.inProgress.forEach((value, key) => {
          statusPromises.push(this.getPipelineStatus(key));
        });

        const resolve = await Promise.all(statusPromises);

        const completeStates: string[] = [];

        for (const res of resolve) {
          if (
            res.data.state === 'COMPLETED' &&
            this.inProgress.has(res.data.id)
          ) {
            const progressData = this.inProgress.get(res.data.id)!;
            completeStates.push(progressData.stateId);
            this.inProgress.delete(res.data.id);
          }
        }

        // console.log(completeStates);

        if (completeStates.length > 0) {
          this.$emitter.emit(PipelineEvents.CHECK_QUEUE_STATUS, completeStates);
        }
        this.checkingStatus = false;
      }
    } catch (error) {
      console.log(error);
      this.checkingStatus = false;
    }
  }

  @OnEvent(AppEvents.SUMMARY_REMOVED)
  summaryRemoved(stateId: string) {
    this.inProgress.delete(stateId);
  }

  isChunkingInProgress(stateId: string): boolean {
    return this.inProgress.has(stateId);
  }

  addStateToProgress(stateId: string, pipelineId: string) {
    this.inProgress.set(pipelineId, { stateId, pipelineId });
  }

  getInferenceConfig(): ModelInfo {
    const model = this.$config.get<string>('evam.model')!;
    const device = this.$config.get<string>('evam.device')!;
    return { model, device };
  }

  availablePipelines(): EvamPipelineOption[] {
    const res: EvamPipelineOption[] = [];

    res.push({
      name: 'Ingestion with Object Detection',
      description:
        'While chunking the video pipeline also processes for object detection',
      value: EVAMPipelines.OBJECT_DETECTION,
    });
    res.push({
      name: 'Simple ingestion',
      description: 'Plain and simple video injestion',
      value: EVAMPipelines.BASIC_INGESTION,
    });

    return res;
  }

  startChunkingStub(
    identifier: string,
    location: string,
    userInputs: SummaryPipelineSampling,
    pipeline: string,
  ) {
    const evamApi = `http://${this.host}:${this.pipelinePort}/pipelines/user_defined_pipelines/${pipeline}`;

    const modelPath = this.$config.get<string>('evam.modelPath')!;
    const device = this.$config.get<string>('evam.device')!;

    const data: ChunkingRequestDTO = {
      source: {
        element: 'curlhttpsrc',
        type: 'gst',
        properties: {
          location,
        },
      },
      parameters: {
        'detection-properties': {
          model: modelPath,
          device,
        },
        publish: {
          minio_bucket: this.$config.get('datastore.bucketName')!,
          video_identifier: identifier,
          topic: this.videoTopic,
        },
        frame: userInputs.samplingFrame,
        chunk_duration: userInputs.chunkDuration,
        frame_width: 480,
      },
    };

    console.log('EVAM URL', evamApi);
    console.log('EVAM DATA', data);

    return this.$http.post<string>(evamApi, data, {
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
