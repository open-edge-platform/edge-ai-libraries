// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { HttpService } from '@nestjs/axios';
import { Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { AxiosRequestConfig } from 'axios';
import { firstValueFrom } from 'rxjs';
import {
  LiveStreamBatchCreateDto,
  LiveStreamBatchDeleteDto,
  LiveStreamBatchRO,
  LiveStreamCreateDto,
  LiveStreamDeleteRO,
  LiveStreamListQueryDto,
  LiveStreamListRO,
  LiveStreamPurgeQueryDto,
  LiveStreamRO,
  LiveStreamUpdateDto,
} from '../models/stream.model';

/**
 * Thin HTTP client for multimodal-dataprep's `/media/streams` surface.
 *
 * Holds no state: dataprep persists stream registrations and restores them
 * across restarts, so a second store here would only create a split brain.
 *
 * Security: `stream_url` may embed `user:password`. Nothing in this class
 * logs a request body, and dataprep redacts the URL in every response, so
 * the credential exists only in transit.
 */
@Injectable()
export class StreamShimService {
  private readonly logger = new Logger(StreamShimService.name);

  constructor(
    private readonly $config: ConfigService,
    private readonly $http: HttpService,
  ) {}

  /** Base URL of dataprep, or an empty string when streams are not deployed. */
  get endpoint(): string {
    return this.$config.get<string>('streams.endpoint') ?? '';
  }

  get isConfigured(): boolean {
    return this.endpoint.length > 0;
  }

  private get timeout(): number {
    return this.$config.get<number>('streams.timeoutMs') ?? 15000;
  }

  private url(...segments: string[]): string {
    return [this.endpoint.replace(/\/+$/, ''), 'media', 'streams', ...segments]
      .filter((segment) => segment.length > 0)
      .join('/');
  }

  /**
   * FastAPI binds `List[str]` from *repeated* keys (`?tags=a&tags=b`).
   * Axios' default array serializer emits `tags[]=a&tags[]=b`, which FastAPI
   * ignores silently — the filter would appear to work and return everything.
   * `indexes: null` produces the repeated-key form.
   */
  private static readonly REPEAT_ARRAY_PARAMS: AxiosRequestConfig['paramsSerializer'] =
    { indexes: null };

  private config(params?: Record<string, unknown>): AxiosRequestConfig {
    return {
      timeout: this.timeout,
      ...(params ? { params } : {}),
      paramsSerializer: StreamShimService.REPEAT_ARRAY_PARAMS,
    };
  }

  create(data: LiveStreamCreateDto): Promise<LiveStreamRO> {
    // Never log `data` - it carries the RTSP credential.
    this.logger.log('Registering a live stream');
    return firstValueFrom(
      this.$http.post<LiveStreamRO>(this.url(), data, this.config()),
    ).then((res) => res.data);
  }

  createBatch(data: LiveStreamBatchCreateDto): Promise<LiveStreamBatchRO> {
    this.logger.log(`Registering ${data.items.length} live stream(s)`);
    return firstValueFrom(
      this.$http.post<LiveStreamBatchRO>(
        this.url('batch'),
        data,
        this.config(),
      ),
    ).then((res) => res.data);
  }

  list(query: LiveStreamListQueryDto = {}): Promise<LiveStreamListRO> {
    const params: Record<string, unknown> = {};
    if (query.state) params.state = query.state;
    if (query.tags?.length) params.tags = query.tags;

    return firstValueFrom(
      this.$http.get<LiveStreamListRO>(this.url(), this.config(params)),
    ).then((res) => res.data);
  }

  get(streamId: string): Promise<LiveStreamRO> {
    return firstValueFrom(
      this.$http.get<LiveStreamRO>(
        this.url(encodeURIComponent(streamId)),
        this.config(),
      ),
    ).then((res) => res.data);
  }

  update(streamId: string, data: LiveStreamUpdateDto): Promise<LiveStreamRO> {
    return firstValueFrom(
      this.$http.patch<LiveStreamRO>(
        this.url(encodeURIComponent(streamId)),
        data,
        this.config(),
      ),
    ).then((res) => res.data);
  }

  remove(
    streamId: string,
    purge: LiveStreamPurgeQueryDto = {},
  ): Promise<LiveStreamDeleteRO> {
    return firstValueFrom(
      this.$http.delete<LiveStreamDeleteRO>(
        this.url(encodeURIComponent(streamId)),
        this.config({
          purge_embeddings: purge.purge_embeddings ?? false,
          purge_media: purge.purge_media ?? false,
        }),
      ),
    ).then((res) => res.data);
  }

  removeBatch(
    data: LiveStreamBatchDeleteDto,
    purge: LiveStreamPurgeQueryDto = {},
  ): Promise<LiveStreamBatchRO> {
    return firstValueFrom(
      this.$http.delete<LiveStreamBatchRO>(this.url(), {
        ...this.config({
          purge_embeddings: purge.purge_embeddings ?? false,
          purge_media: purge.purge_media ?? false,
        }),
        data,
      }),
    ).then((res) => res.data);
  }
}
