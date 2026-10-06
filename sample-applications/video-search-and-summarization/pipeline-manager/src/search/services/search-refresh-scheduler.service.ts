// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import {
  Injectable,
  Logger,
  OnModuleDestroy,
  OnModuleInit,
} from '@nestjs/common';
import { FeaturesEnum, FeaturesService } from 'src/features/features.service';
import { SearchEntity } from '../model/search.entity';
import { SearchDbService } from './search-db.service';
import { SearchIndexVersionService } from './search-index-version.service';
import { SearchRefreshConfigService } from './search-refresh-config.service';
import { SearchStateService } from './search-state.service';

/**
 * Drives automatic refreshes of watched ("checked") search queries.
 *
 * Watched queries used to be re-run on every embeddings event, which scales
 * with ingestion rate rather than with user demand. This scheduler decouples
 * the two: embeddings only mark the index dirty, and a bounded-rate tick
 * decides when — and how many — watched queries are actually re-run.
 *
 * A tick does nothing at all when the index is clean, so an idle deployment
 * costs one integer comparison per interval.
 */
@Injectable()
export class SearchRefreshSchedulerService
  implements OnModuleInit, OnModuleDestroy
{
  private readonly logger = new Logger(SearchRefreshSchedulerService.name);

  private timer: NodeJS.Timeout | null = null;
  private cycleInFlight = false;
  private carryOverQueryIds: string[] = [];

  constructor(
    private $config: SearchRefreshConfigService,
    private $indexVersion: SearchIndexVersionService,
    private $searchDB: SearchDbService,
    private $searchState: SearchStateService,
    private $features: FeaturesService,
  ) {}

  onModuleInit(): void {
    const { enabled, intervalMs } = this.$config.getConfig();

    if (!this.$features.hasFeature(FeaturesEnum.SEARCH)) {
      this.logger.log(
        'Search feature is disabled; watched-query auto refresh not started',
      );
      return;
    }

    if (!enabled) {
      this.logger.log(
        'Watched-query auto refresh is disabled by configuration',
      );
      return;
    }

    this.timer = setInterval(() => {
      void this.tick();
    }, intervalMs);
    this.timer.unref?.();

    this.logger.log(
      `Watched-query auto refresh started with a ${intervalMs} ms interval`,
    );
  }

  onModuleDestroy(): void {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }

  /**
   * One scheduler tick. Exposed for testing; safe to call concurrently because
   * overlapping cycles are skipped rather than queued.
   */
  async tick(): Promise<{ refreshed: number; changed: number } | null> {
    const config = this.$config.getConfig();

    if (this.cycleInFlight) {
      this.logger.debug('Skipping tick: a refresh cycle is still in flight');
      return null;
    }

    const hasCarryOver = this.carryOverQueryIds.length > 0;

    if (!hasCarryOver && !this.$indexVersion.isDirty()) {
      return null;
    }

    if (!hasCarryOver && !this.$indexVersion.isQuiet(config.quietPeriodMs)) {
      this.logger.debug(
        'Skipping tick: still inside the ingestion quiet period',
      );
      return null;
    }

    // Capture the version before the cycle so embeddings that land mid-cycle
    // leave the index dirty for the next tick.
    const versionAtStart = this.$indexVersion.getIndexVersion();
    this.cycleInFlight = true;

    try {
      const { queryIds, hasDeferredWork } = await this.selectQueryIds(config);

      if (queryIds.length === 0) {
        // Only clear the dirty marker when there is genuinely nothing left to
        // do. If queries were skipped because of their minimum refresh
        // interval, the index must stay dirty so a later tick picks them up.
        if (!hasDeferredWork) {
          this.$indexVersion.markRefreshed(versionAtStart);
        }
        return { refreshed: 0, changed: 0 };
      }

      let refreshed = 0;
      let changed = 0;

      for (let i = 0; i < queryIds.length; i += config.batchSize) {
        const batch = queryIds.slice(i, i + config.batchSize);
        const result = await this.$searchState.refreshQueries(batch);
        refreshed += result.refreshed;
        changed += result.changed;
      }

      if (this.carryOverQueryIds.length === 0) {
        this.$indexVersion.markRefreshed(versionAtStart);
      }

      this.logger.log(
        `Auto refresh cycle complete: ${refreshed} watched queries refreshed, ${changed} changed`,
      );

      return { refreshed, changed };
    } catch (error) {
      this.logger.error('Auto refresh cycle failed', error as Error);
      return null;
    } finally {
      this.cycleInFlight = false;
    }
  }

  /**
   * Picks the watched queries to refresh this tick: stalest first, skipping
   * queries refreshed more recently than the per-query minimum interval, and
   * capped at maxQueriesPerTick. Anything above the cap is carried over so a
   * large watch list is drained round-robin instead of all at once.
   */
  private async selectQueryIds(
    config: ReturnType<SearchRefreshConfigService['getConfig']>,
  ): Promise<{ queryIds: string[]; hasDeferredWork: boolean }> {
    const watched = await this.$searchDB.readAllWatched();
    const watchedById = new Map<string, SearchEntity>(
      watched.map((entity) => [entity.queryId, entity]),
    );

    const now = Date.now();
    const isEligible = (entity: SearchEntity): boolean => {
      if (config.minQueryIntervalMs <= 0 || !entity.lastRefreshedAt) {
        return true;
      }
      const last = Date.parse(entity.lastRefreshedAt);
      if (Number.isNaN(last)) {
        return true;
      }
      return now - last >= config.minQueryIntervalMs;
    };

    const carried = this.carryOverQueryIds
      .map((queryId) => watchedById.get(queryId))
      .filter((entity): entity is SearchEntity => !!entity);
    const carriedIds = new Set(carried.map((entity) => entity.queryId));

    const notCarried = watched.filter(
      (entity) => !carriedIds.has(entity.queryId),
    );
    const rateLimitedCount = notCarried.filter(
      (entity) => !isEligible(entity),
    ).length;

    const remaining = notCarried.filter(isEligible).sort((a, b) => {
      const aTime = a.lastRefreshedAt ? Date.parse(a.lastRefreshedAt) : 0;
      const bTime = b.lastRefreshedAt ? Date.parse(b.lastRefreshedAt) : 0;
      return (
        (Number.isNaN(aTime) ? 0 : aTime) - (Number.isNaN(bTime) ? 0 : bTime)
      );
    });

    const ordered = [...carried, ...remaining].map((entity) => entity.queryId);
    const selected = ordered.slice(0, config.maxQueriesPerTick);
    this.carryOverQueryIds = ordered.slice(config.maxQueriesPerTick);

    if (this.carryOverQueryIds.length > 0) {
      this.logger.debug(
        `Deferring ${this.carryOverQueryIds.length} watched queries to the next tick`,
      );
    }

    return {
      queryIds: selected,
      hasDeferredWork:
        this.carryOverQueryIds.length > 0 || rateLimitedCount > 0,
    };
  }
}
