// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { HttpService } from '@nestjs/axios';
import { Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { AxiosResponse } from 'axios';
import { firstValueFrom } from 'rxjs';
import { FrameQueryDto } from '../models/frame.model';

/** The frame bytes plus the headers worth relaying to the browser/agent. */
export interface FrameProxyResult {
  body: Buffer;
  contentType: string;
  frameHeaders: Record<string, string>;
}

/**
 * Thin HTTP client for multimodal-dataprep's `GET /media/frame`.
 *
 * Stateless: a frame is decoded on demand upstream and never persisted, so
 * there is nothing to cache or own here. The request is always made as
 * `arraybuffer` so the raw-JPEG and the `format=json` (base64) variants are
 * relayed byte-for-byte without this layer having to parse either.
 */
@Injectable()
export class FrameShimService {
  private readonly logger = new Logger(FrameShimService.name);

  /** dataprep response headers relayed verbatim to the caller. */
  private static readonly RELAYED_HEADERS = [
    'x-frame-requested-timestamp',
    'x-frame-actual-timestamp',
    'x-frame-width',
    'x-frame-height',
    'x-frame-variant',
    'cache-control',
  ];

  constructor(
    private readonly $config: ConfigService,
    private readonly $http: HttpService,
  ) {}

  /** Base URL of dataprep, or an empty string when search is not deployed. */
  get endpoint(): string {
    return this.$config.get<string>('search.dataPrep') ?? '';
  }

  get isConfigured(): boolean {
    return this.endpoint.length > 0;
  }

  private get timeout(): number {
    return this.$config.get<number>('search.dataPrepTimeoutMs') ?? 30000;
  }

  private get url(): string {
    return [this.endpoint.replace(/\/+$/, ''), 'media', 'frame'].join('/');
  }

  async getFrame(query: FrameQueryDto): Promise<FrameProxyResult> {
    const params: Record<string, unknown> = {
      video_id: query.video_id,
      timestamp: query.timestamp,
    };
    if (query.bucket_name) params.bucket_name = query.bucket_name;
    if (query.media_path) params.media_path = query.media_path;
    if (query.variant) params.variant = query.variant;
    if (query.crop_bbox) params.crop_bbox = query.crop_bbox;
    if (query.format) params.format = query.format;
    if (query.quality !== undefined) params.quality = query.quality;

    this.logger.log(
      `Fetching frame video_id=${query.video_id} t=${query.timestamp} variant=${query.variant ?? 'full'}`,
    );

    const response: AxiosResponse<ArrayBuffer> = await firstValueFrom(
      this.$http.get<ArrayBuffer>(this.url, {
        params,
        timeout: this.timeout,
        responseType: 'arraybuffer',
      }),
    );

    const frameHeaders: Record<string, string> = {};
    for (const name of FrameShimService.RELAYED_HEADERS) {
      const value = response.headers?.[name];
      if (typeof value === 'string') frameHeaders[name] = value;
    }

    return {
      body: Buffer.from(response.data),
      contentType:
        (response.headers?.['content-type'] as string | undefined) ??
        'application/octet-stream',
      frameHeaders,
    };
  }
}
