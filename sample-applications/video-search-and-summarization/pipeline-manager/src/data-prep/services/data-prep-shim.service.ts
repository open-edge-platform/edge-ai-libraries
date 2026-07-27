// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { HttpService } from '@nestjs/axios';
import { Injectable } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { tap } from 'rxjs';
import { SearchEvents } from 'src/events/Pipeline.events';
import {
  DataPrepBatchJobStatusRO,
  DataPrepBatchProcessDTO,
  DataPrepBatchSubmitRO,
  DataPrepMinioDTO,
  DataPrepMinioRO,
  DataPrepSummaryDTO,
} from '../models/data-prep.models';

@Injectable()
export class DataPrepShimService {
  constructor(
    private $config: ConfigService,
    private $http: HttpService,
    private $emitter: EventEmitter2,
  ) {}

  createEmbeddings(data: DataPrepMinioDTO) {
    const dataPrepEndpoint: string =
      this.$config.get<string>('search.dataPrep')!;
    const api = [dataPrepEndpoint, 'media', 'process'].join('/');
    const timeout =
      this.$config.get<number>('search.dataPrepTimeoutMs') ?? 30000;
    return this.$http.post<DataPrepMinioRO>(api, data, { timeout }).pipe(
      tap(() => {
        this.$emitter.emit(SearchEvents.EMBEDDINGS_UPDATE);
      }),
    );
  }

  createEmbeddingsFromSummary(data: DataPrepSummaryDTO) {
    const dataPrepEndpoint: string =
      this.$config.get<string>('search.dataPrep')!;
    const api = [dataPrepEndpoint, 'summary'].join('/');
    const timeout =
      this.$config.get<number>('search.dataPrepTimeoutMs') ?? 30000;

    return this.$http.post<DataPrepMinioRO>(api, data, { timeout }).pipe(
      tap(() => {
        this.$emitter.emit(SearchEvents.EMBEDDINGS_UPDATE);
      }),
    );
  }

  // Submit an async batch job to process several already-stored videos in one
  // request. Returns 202 + { job_id, accepted } immediately; the embeddings are
  // produced in the background and must be polled via getBatchJobStatus().
  createEmbeddingsBatch(data: DataPrepBatchProcessDTO) {
    const dataPrepEndpoint: string =
      this.$config.get<string>('search.dataPrep')!;
    const api = [dataPrepEndpoint, 'media', 'process', 'batch'].join('/');
    const timeout =
      this.$config.get<number>('search.dataPrepTimeoutMs') ?? 30000;

    return this.$http.post<DataPrepBatchSubmitRO>(api, data, { timeout });
  }

  // Poll the status of a previously submitted batch job. When the job reaches a
  // terminal state that produced embeddings, emit EMBEDDINGS_UPDATE so watched
  // searches refresh (parity with the single-video flow).
  getBatchJobStatus(jobId: string) {
    const dataPrepEndpoint: string =
      this.$config.get<string>('search.dataPrep')!;
    const api = [dataPrepEndpoint, 'media', 'jobs', jobId].join('/');
    const timeout =
      this.$config.get<number>('search.dataPrepTimeoutMs') ?? 30000;

    return this.$http.get<DataPrepBatchJobStatusRO>(api, { timeout }).pipe(
      tap((response) => {
        const state = response.data?.state;
        if (
          (state === 'completed' || state === 'completed_with_errors') &&
          (response.data?.completed ?? 0) > 0
        ) {
          this.$emitter.emit(SearchEvents.EMBEDDINGS_UPDATE);
        }
      }),
    );
  }
}
