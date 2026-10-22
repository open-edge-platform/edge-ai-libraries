// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Test, TestingModule } from '@nestjs/testing';
import { HttpService } from '@nestjs/axios';
import { ConfigService } from '@nestjs/config';
import { readFile } from 'node:fs/promises';
import { of, throwError } from 'rxjs';
import { GeoService } from './geo.service';
import { GeoConfig } from '../models/geo.model';

jest.mock('node:fs/promises', () => ({ readFile: jest.fn() }));

const API_BODY = {
  intersections: {
    intersection_1: { label: 'One', lat: 37.5, lon: -122.2 },
    intersection_2: { lat: 37.6, lon: -122.3 },
  },
};

const FALLBACK_BODY = {
  intersections: { intersection_9: { label: 'Fallback', lat: 1, lon: 2 } },
};

describe('GeoService', () => {
  let service: GeoService;
  let httpGet: jest.Mock;
  let geoConfig: Partial<GeoConfig>;
  const readFileMock = readFile as jest.MockedFunction<typeof readFile>;

  const build = async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        GeoService,
        { provide: HttpService, useValue: { get: httpGet } },
        {
          provide: ConfigService,
          useValue: {
            get: jest.fn((key: string) =>
              key === 'geo' ? geoConfig : undefined,
            ),
          },
        },
      ],
    }).compile();
    service = module.get(GeoService);
  };

  beforeEach(() => {
    httpGet = jest.fn();
    readFileMock.mockReset();
    geoConfig = { refreshMs: 60000, timeoutMs: 3000 };
    jest.spyOn(Date, 'now').mockReturnValue(1_000_000);
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('returns source none when nothing is configured', async () => {
    await build();
    await expect(service.getIntersections()).resolves.toEqual({
      source: 'none',
      stale: false,
      fetchedAt: null,
      intersections: {},
    });
    expect(httpGet).not.toHaveBeenCalled();
  });

  it('fetches from the API with timeout and caches within the refresh period', async () => {
    geoConfig.apiUrl = 'http://geo-api/api/v1/intersections';
    httpGet.mockReturnValue(of({ data: API_BODY }));
    await build();

    const first = await service.getIntersections();
    const second = await service.getIntersections();

    expect(first.source).toBe('geo-api');
    expect(first.stale).toBe(false);
    expect(Object.keys(first.intersections)).toEqual([
      'intersection_1',
      'intersection_2',
    ]);
    expect(second).toBe(first);
    expect(httpGet).toHaveBeenCalledTimes(1);
    expect(httpGet).toHaveBeenCalledWith(
      'http://geo-api/api/v1/intersections',
      expect.objectContaining({ timeout: 3000 }),
    );
  });

  it('serves the last API data as stale when a later refresh fails', async () => {
    geoConfig.apiUrl = 'http://geo-api/api/v1/intersections';
    httpGet.mockReturnValueOnce(of({ data: API_BODY }));
    await build();
    await service.getIntersections();

    httpGet.mockReturnValueOnce(throwError(() => new Error('ECONNREFUSED')));
    (Date.now as jest.Mock).mockReturnValue(1_000_000 + 60001);
    await service.refresh();

    const result = await service.getIntersections();
    expect(result.source).toBe('geo-api');
    expect(result.stale).toBe(true);
    expect(Object.keys(result.intersections)).toEqual([
      'intersection_1',
      'intersection_2',
    ]);
  });

  it('refreshes in the background after the refresh period and returns the cached copy', async () => {
    geoConfig.apiUrl = 'http://geo-api/api/v1/intersections';
    httpGet.mockReturnValue(of({ data: API_BODY }));
    await build();
    const first = await service.getIntersections();

    (Date.now as jest.Mock).mockReturnValue(1_000_000 + 60001);
    const second = await service.getIntersections();

    expect(second).toBe(first);
    expect(httpGet).toHaveBeenCalledTimes(2);
  });

  it('uses the fallback file, marked stale, when the API has never answered', async () => {
    geoConfig.apiUrl = 'http://geo-api/api/v1/intersections';
    geoConfig.fallbackFile = '/app/config/geo-intersections.json';
    httpGet.mockReturnValue(throwError(() => new Error('timeout')));
    readFileMock.mockResolvedValue(JSON.stringify(FALLBACK_BODY));
    await build();

    const result = await service.getIntersections();
    expect(result.source).toBe('fallback');
    expect(result.stale).toBe(true);
    expect(Object.keys(result.intersections)).toEqual(['intersection_9']);
    expect(readFileMock).toHaveBeenCalledWith(
      '/app/config/geo-intersections.json',
      'utf8',
    );
  });

  it('uses the fallback file as not stale when no API url is configured', async () => {
    geoConfig.fallbackFile = '/app/config/geo-intersections.json';
    readFileMock.mockResolvedValue(JSON.stringify(FALLBACK_BODY));
    await build();

    const result = await service.getIntersections();
    expect(result.source).toBe('fallback');
    expect(result.stale).toBe(false);
  });

  it('returns source none when the fallback file is not valid JSON', async () => {
    geoConfig.fallbackFile = '/app/config/geo-intersections.json';
    readFileMock.mockResolvedValue('{ not json');
    await build();

    const result = await service.getIntersections();
    expect(result.source).toBe('none');
    expect(result.intersections).toEqual({});
  });

  it('makes a single API call for concurrent first requests', async () => {
    geoConfig.apiUrl = 'http://geo-api/api/v1/intersections';
    httpGet.mockReturnValue(of({ data: API_BODY }));
    await build();

    await Promise.all([
      service.getIntersections(),
      service.getIntersections(),
      service.getIntersections(),
    ]);
    expect(httpGet).toHaveBeenCalledTimes(1);
  });
});
