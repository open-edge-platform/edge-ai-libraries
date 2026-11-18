// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { HttpService } from '@nestjs/axios';
import { Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { readFile } from 'node:fs/promises';
import { firstValueFrom } from 'rxjs';
import {
  GeoConfig,
  GeoIntersectionsRO,
  normalizeIntersections,
} from '../models/geo.model';

const EMPTY: GeoIntersectionsRO = {
  source: 'none',
  stale: false,
  fetchedAt: null,
  intersections: {},
};

const MAX_RESPONSE_BYTES = 1_000_000;

@Injectable()
export class GeoService {
  private readonly logger = new Logger(GeoService.name);
  private cache: GeoIntersectionsRO | null = null;
  private fetchedAtMs = 0;
  private inflight: Promise<void> | null = null;

  constructor(
    private $http: HttpService,
    private $config: ConfigService,
  ) {}

  private get config(): GeoConfig {
    const geo = this.$config.get<Partial<GeoConfig>>('geo') ?? {};
    return {
      apiUrl: geo.apiUrl || undefined,
      fallbackFile: geo.fallbackFile || undefined,
      refreshMs:
        typeof geo.refreshMs === 'number' && geo.refreshMs > 0
          ? geo.refreshMs
          : 60000,
      timeoutMs:
        typeof geo.timeoutMs === 'number' && geo.timeoutMs > 0
          ? geo.timeoutMs
          : 3000,
    };
  }

  async getIntersections(): Promise<GeoIntersectionsRO> {
    if (!this.cache) {
      await this.refresh();
    } else if (Date.now() - this.fetchedAtMs > this.config.refreshMs) {
      // Serve the cached copy; the next request sees the refreshed data.
      void this.refresh();
    }
    return this.cache ?? EMPTY;
  }

  refresh(): Promise<void> {
    this.inflight ??= this.doRefresh().finally(() => {
      this.inflight = null;
    });
    return this.inflight;
  }

  private warn = (message: string) => this.logger.warn(message);

  private async doRefresh(): Promise<void> {
    const { apiUrl, timeoutMs } = this.config;

    if (apiUrl) {
      try {
        const res = await firstValueFrom(
          this.$http.get<unknown>(apiUrl, {
            timeout: timeoutMs,
            maxContentLength: MAX_RESPONSE_BYTES,
          }),
        );
        const body = res.data as { intersections?: unknown } | null;
        if (
          typeof body?.intersections !== 'object' ||
          body.intersections === null
        ) {
          throw new Error('response has no intersections object');
        }
        if (this.cache?.source !== 'geo-api') {
          this.logger.log('geo: using intersections from the API');
        }
        this.cache = {
          source: 'geo-api',
          stale: false,
          fetchedAt: new Date().toISOString(),
          intersections: normalizeIntersections(res.data, this.warn),
        };
        this.fetchedAtMs = Date.now();
        return;
      } catch (error) {
        this.logger.warn(
          `geo: intersections API request failed: ${(error as Error).message}`,
        );
        if (this.cache?.source === 'geo-api') {
          this.cache = { ...this.cache, stale: true };
          this.fetchedAtMs = Date.now();
          return;
        }
      }
    }

    this.cache = await this.loadFallback();
    this.fetchedAtMs = Date.now();
  }

  private async loadFallback(): Promise<GeoIntersectionsRO> {
    const { fallbackFile, apiUrl } = this.config;
    if (!fallbackFile) return EMPTY;
    try {
      const raw: unknown = JSON.parse(await readFile(fallbackFile, 'utf8'));
      return {
        source: 'fallback',
        stale: Boolean(apiUrl),
        fetchedAt: new Date().toISOString(),
        intersections: normalizeIntersections(raw, this.warn),
      };
    } catch (error) {
      this.logger.warn(
        `geo: fallback file unreadable: ${(error as Error).message}`,
      );
      return EMPTY;
    }
  }
}
