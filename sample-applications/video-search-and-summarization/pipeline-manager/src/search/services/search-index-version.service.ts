// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Injectable, Logger } from '@nestjs/common';
import { OnEvent } from '@nestjs/event-emitter';
import { SearchEvents } from 'src/events/Pipeline.events';

/**
 * Tracks how "dirty" the vector index is.
 *
 * New embeddings no longer re-run watched search queries directly. They only
 * bump an in-memory version counter, which the refresh scheduler compares
 * against the version it last refreshed for. This keeps the cost of an
 * embedding event constant regardless of ingestion frequency, and lets the
 * scheduler skip work entirely when nothing new was indexed.
 */
@Injectable()
export class SearchIndexVersionService {
  private readonly logger = new Logger(SearchIndexVersionService.name);

  private indexVersion = 0;
  private refreshedVersion = 0;
  private lastEmbeddingAt: number | null = null;

  @OnEvent(SearchEvents.EMBEDDINGS_UPDATE)
  markDirty(): void {
    this.indexVersion += 1;
    this.lastEmbeddingAt = Date.now();
    this.logger.debug(
      `Search index marked dirty (version ${this.indexVersion})`,
    );
  }

  getIndexVersion(): number {
    return this.indexVersion;
  }

  getLastEmbeddingAt(): number | null {
    return this.lastEmbeddingAt;
  }

  isDirty(): boolean {
    return this.indexVersion !== this.refreshedVersion;
  }

  /**
   * Returns true when the most recent embedding event is older than the quiet
   * period, i.e. the ingestion burst has settled enough to refresh.
   */
  isQuiet(quietPeriodMs: number, now: number = Date.now()): boolean {
    if (quietPeriodMs <= 0 || this.lastEmbeddingAt === null) {
      return true;
    }
    return now - this.lastEmbeddingAt >= quietPeriodMs;
  }

  /**
   * Records the index version a refresh cycle ran against. Capturing the
   * version *before* the cycle starts ensures embeddings that land mid-cycle
   * still leave the index dirty for the next tick.
   */
  markRefreshed(version: number): void {
    this.refreshedVersion = version;
  }
}
