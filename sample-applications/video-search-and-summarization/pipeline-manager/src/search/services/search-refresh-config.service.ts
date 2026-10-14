// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';

export interface SearchWatchRefreshConfig {
  enabled: boolean;
  intervalMs: number;
  quietPeriodMs: number;
  batchSize: number;
  minQueryIntervalMs: number;
  maxQueriesPerTick: number;
}

/**
 * Resolves and validates the auto-refresh configuration for watched search
 * queries. Operator-supplied values are clamped to safe bounds so a bad
 * environment value can never turn the scheduler into a busy loop or an
 * unbounded fan-out.
 */
@Injectable()
export class SearchRefreshConfigService {
  static readonly MIN_INTERVAL_MS = 1000;
  static readonly MAX_INTERVAL_MS = 3600000;
  static readonly MAX_QUIET_PERIOD_MS = 300000;
  static readonly MAX_BATCH_SIZE = 100;
  static readonly MAX_QUERIES_PER_TICK = 500;
  static readonly MAX_MIN_QUERY_INTERVAL_MS = 3600000;

  private readonly logger = new Logger(SearchRefreshConfigService.name);
  private readonly config: SearchWatchRefreshConfig;

  constructor(private $config: ConfigService) {
    this.config = this.resolve();
    this.logger.log(
      `Watched-query auto refresh resolved config: ${JSON.stringify(this.config)}`,
    );
  }

  getConfig(): SearchWatchRefreshConfig {
    return { ...this.config };
  }

  private resolve(): SearchWatchRefreshConfig {
    const intervalMs = this.readBoundedInteger(
      'search.watchRefresh.intervalMs',
      10000,
      SearchRefreshConfigService.MIN_INTERVAL_MS,
      SearchRefreshConfigService.MAX_INTERVAL_MS,
    );

    return {
      enabled: this.readBoolean('search.watchRefresh.enabled', true),
      intervalMs,
      quietPeriodMs: this.readBoundedInteger(
        'search.watchRefresh.quietPeriodMs',
        2000,
        0,
        SearchRefreshConfigService.MAX_QUIET_PERIOD_MS,
      ),
      batchSize: this.readBoundedInteger(
        'search.watchRefresh.batchSize',
        10,
        1,
        SearchRefreshConfigService.MAX_BATCH_SIZE,
      ),
      minQueryIntervalMs: this.readBoundedInteger(
        'search.watchRefresh.minQueryIntervalMs',
        10000,
        0,
        SearchRefreshConfigService.MAX_MIN_QUERY_INTERVAL_MS,
      ),
      maxQueriesPerTick: this.readBoundedInteger(
        'search.watchRefresh.maxQueriesPerTick',
        50,
        1,
        SearchRefreshConfigService.MAX_QUERIES_PER_TICK,
      ),
    };
  }

  private readBoolean(key: string, fallback: boolean): boolean {
    const value = this.$config.get<string | boolean>(key);
    if (value === undefined || value === null || value === '') {
      return fallback;
    }
    if (typeof value === 'boolean') {
      return value;
    }
    const normalized = String(value).trim().toLowerCase();
    if (['true', '1', 'yes', 'on'].includes(normalized)) {
      return true;
    }
    if (['false', '0', 'no', 'off'].includes(normalized)) {
      return false;
    }
    this.logger.warn(
      `Invalid boolean value "${value}" for ${key}; falling back to ${fallback}`,
    );
    return fallback;
  }

  private readBoundedInteger(
    key: string,
    fallback: number,
    min: number,
    max: number,
  ): number {
    const raw = this.$config.get<number | string>(key);
    const parsed = typeof raw === 'string' ? Number(raw) : raw;

    if (typeof parsed !== 'number' || !Number.isFinite(parsed)) {
      return fallback;
    }

    const floored = Math.floor(parsed);
    const clamped = Math.min(Math.max(floored, min), max);
    if (clamped !== floored) {
      this.logger.warn(
        `Value ${floored} for ${key} is out of range [${min}, ${max}]; using ${clamped}`,
      );
    }
    return clamped;
  }
}
