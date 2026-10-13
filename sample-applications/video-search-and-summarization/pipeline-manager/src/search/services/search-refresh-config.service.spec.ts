// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { ConfigService } from '@nestjs/config';
import { SearchRefreshConfigService } from './search-refresh-config.service';

const configServiceWith = (values: Record<string, unknown>): ConfigService =>
  ({
    get: (key: string) => values[key],
  }) as unknown as ConfigService;

describe('SearchRefreshConfigService', () => {
  it('should apply defaults when nothing is configured', () => {
    const service = new SearchRefreshConfigService(configServiceWith({}));

    expect(service.getConfig()).toEqual({
      enabled: true,
      intervalMs: 10000,
      quietPeriodMs: 2000,
      batchSize: 10,
      minQueryIntervalMs: 10000,
      maxQueriesPerTick: 50,
    });
  });

  it('should clamp out-of-range values to safe bounds', () => {
    const service = new SearchRefreshConfigService(
      configServiceWith({
        'search.watchRefresh.intervalMs': 0,
        'search.watchRefresh.batchSize': 100000,
        'search.watchRefresh.quietPeriodMs': -5,
        'search.watchRefresh.maxQueriesPerTick': 0,
      }),
    );

    const config = service.getConfig();
    expect(config.intervalMs).toBe(SearchRefreshConfigService.MIN_INTERVAL_MS);
    expect(config.batchSize).toBe(SearchRefreshConfigService.MAX_BATCH_SIZE);
    expect(config.quietPeriodMs).toBe(0);
    expect(config.maxQueriesPerTick).toBe(1);
  });

  it('should fall back to defaults for non-numeric values', () => {
    const service = new SearchRefreshConfigService(
      configServiceWith({ 'search.watchRefresh.intervalMs': 'not-a-number' }),
    );

    expect(service.getConfig().intervalMs).toBe(10000);
  });

  it('should parse string booleans for the enabled flag', () => {
    expect(
      new SearchRefreshConfigService(
        configServiceWith({ 'search.watchRefresh.enabled': 'false' }),
      ).getConfig().enabled,
    ).toBe(false);

    expect(
      new SearchRefreshConfigService(
        configServiceWith({ 'search.watchRefresh.enabled': 'true' }),
      ).getConfig().enabled,
    ).toBe(true);

    expect(
      new SearchRefreshConfigService(
        configServiceWith({ 'search.watchRefresh.enabled': 'maybe' }),
      ).getConfig().enabled,
    ).toBe(true);
  });

  it('should return a copy so callers cannot mutate the resolved config', () => {
    const service = new SearchRefreshConfigService(configServiceWith({}));
    const config = service.getConfig();
    config.intervalMs = 1;

    expect(service.getConfig().intervalMs).toBe(10000);
  });
});
