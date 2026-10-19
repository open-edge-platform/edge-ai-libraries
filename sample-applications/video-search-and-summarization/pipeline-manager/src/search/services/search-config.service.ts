// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { BadRequestException, Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';

export interface SearchConfig {
  /** Minimum peak score applied when a query does not set its own; 0 = off. */
  minPeakScoreDefault: number;
}

/**
 * Search behaviour settings shared by the API, the UI and the search runs.
 *
 * The minimum peak score is the lowest frame similarity a search keeps. It is
 * pushed down to retrieval, so the returned top-N are all above it rather
 * than the top-N trimmed afterwards.
 */
@Injectable()
export class SearchConfigService {
  static readonly MIN_PEAK_SCORE_MIN = 0;
  static readonly MIN_PEAK_SCORE_MAX = 1;

  private readonly logger = new Logger(SearchConfigService.name);
  private readonly minPeakScoreDefault: number;

  constructor(private $config: ConfigService) {
    this.minPeakScoreDefault = this.readDefaultMinPeakScore();
    this.logger.log(`Default minimum peak score: ${this.minPeakScoreDefault}`);
  }

  getConfig(): SearchConfig {
    return { minPeakScoreDefault: this.minPeakScoreDefault };
  }

  getDefaultMinPeakScore(): number {
    return this.minPeakScoreDefault;
  }

  static isValidMinPeakScore(value: unknown): value is number {
    return (
      typeof value === 'number' &&
      Number.isFinite(value) &&
      value >= SearchConfigService.MIN_PEAK_SCORE_MIN &&
      value <= SearchConfigService.MIN_PEAK_SCORE_MAX
    );
  }

  /**
   * Validate a client-supplied minimum peak score. `undefined`/`null` mean
   * "not set" and are returned as `undefined`; anything else must be a number
   * in [0, 1].
   */
  parseMinPeakScore(value: unknown): number | undefined {
    if (value === undefined || value === null) {
      return undefined;
    }
    if (!SearchConfigService.isValidMinPeakScore(value)) {
      throw new BadRequestException(
        'minPeakScore must be a number between 0 and 1.',
      );
    }
    return value;
  }

  /** First set value of the arguments, else the configured default. */
  resolveMinPeakScore(...candidates: (number | null | undefined)[]): number {
    for (const candidate of candidates) {
      if (SearchConfigService.isValidMinPeakScore(candidate)) {
        return candidate;
      }
    }
    return this.minPeakScoreDefault;
  }

  private readDefaultMinPeakScore(): number {
    const raw = this.$config.get<string | number>('search.minPeakScore');
    if (raw === undefined || raw === null || raw === '') {
      return 0;
    }
    const value = Number(raw);
    if (!SearchConfigService.isValidMinPeakScore(value)) {
      this.logger.warn(
        `Ignoring invalid SEARCH_MIN_PEAK_SCORE=${String(raw)}; expected a number in [0, 1]. Using 0.`,
      );
      return 0;
    }
    return value;
  }
}
