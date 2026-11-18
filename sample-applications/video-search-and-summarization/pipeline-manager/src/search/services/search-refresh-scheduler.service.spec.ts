// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { FeaturesEnum } from 'src/features/features.service';
import type { FeaturesService } from 'src/features/features.service';
import type { SearchEntity } from '../model/search.entity';
import type { SearchDbService } from './search-db.service';
import { SearchIndexVersionService } from './search-index-version.service';
import type {
  SearchRefreshConfigService,
  SearchWatchRefreshConfig,
} from './search-refresh-config.service';
import { SearchRefreshSchedulerService } from './search-refresh-scheduler.service';

// The scheduler depends on SearchStateService, which pulls in the ESM-only
// uuid package; mock it the same way the SearchStateService spec does.
jest.mock('uuid', () => ({ v4: jest.fn(() => 'mock-query-id') }));
import type { SearchStateService } from './search-state.service';

describe('SearchRefreshSchedulerService', () => {
  const defaultConfig: SearchWatchRefreshConfig = {
    enabled: true,
    intervalMs: 10000,
    quietPeriodMs: 2000,
    batchSize: 2,
    minQueryIntervalMs: 0,
    maxQueriesPerTick: 50,
  };

  let config: SearchWatchRefreshConfig;
  let configService: SearchRefreshConfigService;
  let indexVersion: SearchIndexVersionService;
  let searchDb: jest.Mocked<Pick<SearchDbService, 'readAllWatched'>>;
  let searchState: jest.Mocked<Pick<SearchStateService, 'refreshQueries'>>;
  let features: jest.Mocked<Pick<FeaturesService, 'hasFeature'>>;
  let scheduler: SearchRefreshSchedulerService;

  const watched = (queryId: string, lastRefreshedAt?: string): SearchEntity =>
    ({ queryId, watch: true, lastRefreshedAt }) as SearchEntity;

  beforeEach(() => {
    config = { ...defaultConfig };
    configService = {
      getConfig: () => ({ ...config }),
    } as unknown as SearchRefreshConfigService;
    indexVersion = new SearchIndexVersionService();
    searchDb = { readAllWatched: jest.fn().mockResolvedValue([]) } as any;
    searchState = {
      refreshQueries: jest.fn().mockImplementation(async (ids: string[]) => ({
        refreshed: ids.length,
        changed: 0,
      })),
    } as any;
    features = { hasFeature: jest.fn().mockReturnValue(true) } as any;

    scheduler = new SearchRefreshSchedulerService(
      configService,
      indexVersion,
      searchDb as unknown as SearchDbService,
      searchState as unknown as SearchStateService,
      features as unknown as FeaturesService,
    );
  });

  afterEach(() => {
    scheduler.onModuleDestroy();
    jest.useRealTimers();
    jest.restoreAllMocks();
  });

  describe('tick', () => {
    it('should do nothing when the index is clean', async () => {
      const result = await scheduler.tick();

      expect(result).toBeNull();
      expect(searchDb.readAllWatched).not.toHaveBeenCalled();
      expect(searchState.refreshQueries).not.toHaveBeenCalled();
    });

    it('should skip while inside the ingestion quiet period', async () => {
      indexVersion.markDirty();

      const result = await scheduler.tick();

      expect(result).toBeNull();
      expect(searchState.refreshQueries).not.toHaveBeenCalled();
    });

    it('should refresh watched queries once the quiet period elapsed', async () => {
      indexVersion.markDirty();
      jest.spyOn(indexVersion, 'isQuiet').mockReturnValue(true);
      searchDb.readAllWatched.mockResolvedValue([
        watched('query-1'),
        watched('query-2'),
      ]);

      const result = await scheduler.tick();

      expect(result).toEqual({ refreshed: 2, changed: 0 });
      expect(searchState.refreshQueries).toHaveBeenCalledWith([
        'query-1',
        'query-2',
      ]);
      expect(indexVersion.isDirty()).toBe(false);
    });

    it('should split work into batches of batchSize', async () => {
      config.batchSize = 2;
      indexVersion.markDirty();
      jest.spyOn(indexVersion, 'isQuiet').mockReturnValue(true);
      searchDb.readAllWatched.mockResolvedValue([
        watched('q1'),
        watched('q2'),
        watched('q3'),
      ]);

      await scheduler.tick();

      expect(searchState.refreshQueries).toHaveBeenCalledTimes(2);
      expect(searchState.refreshQueries).toHaveBeenNthCalledWith(1, [
        'q1',
        'q2',
      ]);
      expect(searchState.refreshQueries).toHaveBeenNthCalledWith(2, ['q3']);
    });

    it('should cap queries per tick and carry the remainder over', async () => {
      config.maxQueriesPerTick = 1;
      config.batchSize = 10;
      indexVersion.markDirty();
      jest.spyOn(indexVersion, 'isQuiet').mockReturnValue(true);
      searchDb.readAllWatched.mockResolvedValue([watched('q1'), watched('q2')]);

      await scheduler.tick();
      expect(searchState.refreshQueries).toHaveBeenNthCalledWith(1, ['q1']);

      // Index is no longer dirty, but the carry-over still gets drained.
      await scheduler.tick();
      expect(searchState.refreshQueries).toHaveBeenNthCalledWith(2, ['q2']);
    });

    it('should skip queries refreshed more recently than minQueryIntervalMs', async () => {
      config.minQueryIntervalMs = 60000;
      indexVersion.markDirty();
      jest.spyOn(indexVersion, 'isQuiet').mockReturnValue(true);
      searchDb.readAllWatched.mockResolvedValue([
        watched('fresh', new Date().toISOString()),
        watched('stale', new Date(Date.now() - 120000).toISOString()),
      ]);

      await scheduler.tick();

      expect(searchState.refreshQueries).toHaveBeenCalledWith(['stale']);
    });

    it('should refresh the stalest queries first', async () => {
      indexVersion.markDirty();
      jest.spyOn(indexVersion, 'isQuiet').mockReturnValue(true);
      config.batchSize = 10;
      searchDb.readAllWatched.mockResolvedValue([
        watched('newer', new Date(Date.now() - 1000).toISOString()),
        watched('older', new Date(Date.now() - 100000).toISOString()),
        watched('never'),
      ]);

      await scheduler.tick();

      expect(searchState.refreshQueries).toHaveBeenCalledWith([
        'never',
        'older',
        'newer',
      ]);
    });

    it('should not run overlapping cycles', async () => {
      indexVersion.markDirty();
      jest.spyOn(indexVersion, 'isQuiet').mockReturnValue(true);
      searchDb.readAllWatched.mockResolvedValue([watched('q1')]);

      let release: () => void = () => undefined;
      searchState.refreshQueries.mockImplementation(
        () =>
          new Promise((resolve) => {
            release = () => resolve({ refreshed: 1, changed: 0 });
          }),
      );

      const first = scheduler.tick();
      await Promise.resolve();
      const second = await scheduler.tick();

      expect(second).toBeNull();
      expect(searchState.refreshQueries).toHaveBeenCalledTimes(1);

      release();
      await first;
    });

    it('should clear the in-flight guard when a cycle throws', async () => {
      indexVersion.markDirty();
      jest.spyOn(indexVersion, 'isQuiet').mockReturnValue(true);
      searchDb.readAllWatched.mockRejectedValueOnce(new Error('db down'));

      const result = await scheduler.tick();

      expect(result).toBeNull();

      indexVersion.markDirty();
      searchDb.readAllWatched.mockResolvedValue([watched('q1')]);
      await expect(scheduler.tick()).resolves.toEqual({
        refreshed: 1,
        changed: 0,
      });
    });

    it('should stay dirty when every watched query is rate limited', async () => {
      config.minQueryIntervalMs = 60000;
      indexVersion.markDirty();
      jest.spyOn(indexVersion, 'isQuiet').mockReturnValue(true);
      searchDb.readAllWatched.mockResolvedValue([
        watched('fresh', new Date().toISOString()),
      ]);

      const result = await scheduler.tick();

      expect(result).toEqual({ refreshed: 0, changed: 0 });
      expect(searchState.refreshQueries).not.toHaveBeenCalled();
      expect(indexVersion.isDirty()).toBe(true);
    });

    it('should mark the index refreshed even when nothing is watched', async () => {
      indexVersion.markDirty();
      jest.spyOn(indexVersion, 'isQuiet').mockReturnValue(true);

      const result = await scheduler.tick();

      expect(result).toEqual({ refreshed: 0, changed: 0 });
      expect(indexVersion.isDirty()).toBe(false);
    });
  });

  describe('lifecycle', () => {
    it('should not start when the search feature is off', () => {
      features.hasFeature.mockReturnValue(false);

      scheduler.onModuleInit();

      expect(features.hasFeature).toHaveBeenCalledWith(FeaturesEnum.SEARCH);
      expect(jest.getTimerCount?.() ?? 0).toBe(0);
    });

    it('should not start when auto refresh is disabled', () => {
      jest.useFakeTimers();
      config.enabled = false;

      scheduler.onModuleInit();

      expect(jest.getTimerCount()).toBe(0);
    });

    it('should tick on the configured interval and stop on destroy', () => {
      jest.useFakeTimers();
      const tickSpy = jest.spyOn(scheduler, 'tick').mockResolvedValue(null);

      scheduler.onModuleInit();
      jest.advanceTimersByTime(config.intervalMs * 2);

      expect(tickSpy).toHaveBeenCalledTimes(2);

      scheduler.onModuleDestroy();
      jest.advanceTimersByTime(config.intervalMs * 2);

      expect(tickSpy).toHaveBeenCalledTimes(2);
    });
  });
});
