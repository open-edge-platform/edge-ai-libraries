// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { HttpService } from '@nestjs/axios';
import { Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { isAxiosError } from 'axios';
import { defer, retry, tap, timer } from 'rxjs';
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
  private static readonly RETRYABLE_POLL_STATUS_CODES = new Set([
    408, 429, 500, 502, 503, 504,
  ]);

  private static readonly RETRYABLE_POLL_ERROR_CODES = new Set([
    'ECONNABORTED',
    'ECONNREFUSED',
    'ECONNRESET',
    'EPIPE',
    'ETIMEDOUT',
    'EAI_AGAIN',
  ]);

  constructor(
    private $config: ConfigService,
    private $http: HttpService,
    private $emitter: EventEmitter2,
  ) {}

  private getNonNegativeInteger(key: string, fallback: number): number {
    const value = this.$config.get<number>(key);
    return typeof value === 'number' && Number.isFinite(value)
      ? Math.max(0, Math.floor(value))
      : fallback;
  }

  private isRetryableBatchPollError(error: unknown): boolean {
    if (!isAxiosError(error)) {
      return false;
    }

    if (error.response?.status !== undefined) {
      return DataPrepShimService.RETRYABLE_POLL_STATUS_CODES.has(
        error.response.status,
      );
    }

    return DataPrepShimService.RETRYABLE_POLL_ERROR_CODES.has(error.code ?? '');
  }

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
    const timeout = this.getNonNegativeInteger(
      'search.dataPrepPollTimeoutMs',
      10000,
    );
    const maxRetries = this.getNonNegativeInteger(
      'search.dataPrepPollMaxRetries',
      3,
    );
    const retryDelayMs = this.getNonNegativeInteger(
      'search.dataPrepPollRetryDelayMs',
      500,
    );

    return defer(() =>
      this.$http.get<DataPrepBatchJobStatusRO>(api, { timeout }),
    ).pipe(
      retry({
        count: maxRetries,
        delay: (error, retryCount) => {
          if (!this.isRetryableBatchPollError(error)) {
            throw error;
          }

          const delayMs = retryDelayMs * 2 ** (retryCount - 1);
          const reason = isAxiosError(error)
            ? error.response?.status
              ? `HTTP ${error.response.status}`
              : (error.code ?? 'network error')
            : 'unknown error';
          Logger.warn(
            `Transient DataPrep batch-status poll failure (${reason}); ` +
              `retrying ${retryCount}/${maxRetries} in ${delayMs} ms`,
          );
          return timer(delayMs);
        },
      }),
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
