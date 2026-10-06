// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Test, TestingModule } from '@nestjs/testing';
import { SearchStateService } from './search-state.service';
import { SearchDbService } from './search-db.service';
import { VideoService } from 'src/video-upload/services/video.service';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { SearchShimService } from './search-shim.service';
import { SearchQueryStatus, SearchResultBody } from '../model/search.model';
import { SearchEntity } from '../model/search.entity';
import { VideoEntity } from 'src/video-upload/models/video.entity';
import { of, throwError } from 'rxjs';
import { SearchEvents } from 'src/events/Pipeline.events';
import { SocketEvent } from 'src/events/socket.events';

jest.mock('uuid', () => ({
  v4: jest.fn(() => 'mock-query-id'),
}));

describe('SearchStateService', () => {
  let service: SearchStateService;
  let searchDbService: jest.Mocked<SearchDbService>;
  let videoService: jest.Mocked<VideoService>;
  let eventEmitter: jest.Mocked<EventEmitter2>;
  let searchShimService: jest.Mocked<SearchShimService>;

  beforeEach(async () => {
    const mockSearchDbService = {
      readAll: jest.fn(),
      create: jest.fn(),
      read: jest.fn(),
      updateWatch: jest.fn(),
      updateQueryStatus: jest.fn(),
      updateQueryStatusWithError: jest.fn(),
      addResults: jest.fn(),
      markRefreshed: jest.fn(),
      readAllWatched: jest.fn(),
      update: jest.fn(),
    };

    const mockVideoService = {
      getVideos: jest.fn().mockResolvedValue([]),
    };

    const mockEventEmitter = {
      emit: jest.fn(),
    };

    const mockSearchShimService = {
      search: jest.fn(),
    };

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        SearchStateService,
        {
          provide: SearchDbService,
          useValue: mockSearchDbService,
        },
        {
          provide: VideoService,
          useValue: mockVideoService,
        },
        {
          provide: EventEmitter2,
          useValue: mockEventEmitter,
        },
        {
          provide: SearchShimService,
          useValue: mockSearchShimService,
        },
      ],
    }).compile();

    service = module.get<SearchStateService>(SearchStateService);
    searchDbService = module.get(SearchDbService);
    videoService = module.get(VideoService);
    eventEmitter = module.get(EventEmitter2);
    searchShimService = module.get(SearchShimService);
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  describe('buildTimeFilterRange', () => {
    it('should build relative time range', () => {
      const result = service.buildTimeFilterRange({ value: 1, unit: 'hours' });

      expect(result.range).not.toBeNull();
      expect(result.selection?.source).toBe('relative');
    });

    it('should preserve valid absolute time range', () => {
      const result = service.buildTimeFilterRange({
        start: '2026-06-24T05:00:00Z',
        end: '2026-06-24T06:00:00Z',
      });

      expect(result.range).toEqual({
        start: '2026-06-24T05:00:00.000Z',
        end: '2026-06-24T06:00:00.000Z',
      });
      expect(result.selection?.source).toBe('absolute');
    });

    it('should reject invalid absolute time range', () => {
      const result = service.buildTimeFilterRange({
        start: '2026-06-24T06:00:00Z',
        end: '2026-06-24T05:00:00Z',
      });

      expect(result).toEqual({ selection: null, range: null });
    });
  });

  describe('getQueries', () => {
    it('should return enriched queries with videos', async () => {
      const mockQueries: SearchEntity[] = [
        {
          queryId: 'query-1',
          query: 'test query',
          watch: false,
          queryStatus: SearchQueryStatus.IDLE,
          tags: [],
          results: [
            {
              id: 'result-1',
              page_content: 'test content',
              type: 'test',
              metadata: {
                video_id: 'video-1',
                bucket_name: 'test-bucket',
                clip_duration: 30,
                date: '2025-01-01',
                date_time: '2025-01-01T00:00:00Z',
                day: 1,
                fps: 30,
                frames_in_clip: 900,
                hours: 0,
                id: 'test-id',
                interval_num: 1,
                minutes: 0,
                month: 1,
                seconds: 0,
                time: '00:00:00',
                timestamp: 1640995200,
                total_frames: 900,
                video: 'test-video',
                video_path: '/test/path',
                video_rel_url: '/rel/path',
                video_remote_path: '/remote/path',
                video_url: 'http://test.com/video',
                year: 2025,
                relevance_score: 0.95,
              },
            },
          ],
          createdAt: '2025-01-01T00:00:00.000Z',
          updatedAt: '2025-01-01T00:00:00.000Z',
        },
      ];

      const mockVideos: VideoEntity[] = [
        {
          videoId: 'video-1',
          name: 'test-video',
          url: '/test/path',
          videoName: 'test-video',
          videoPath: '/test/path',
          tags: [],
          createdAt: '2025-01-01T00:00:00.000Z',
          updatedAt: '2025-01-01T00:00:00.000Z',
        } as VideoEntity,
      ];

      searchDbService.readAll.mockResolvedValue(mockQueries);
      videoService.getVideos.mockResolvedValue(mockVideos);

      const result = await service.getQueries();

      expect(searchDbService.readAll).toHaveBeenCalled();
      expect(videoService.getVideos).toHaveBeenCalled();
      expect(result).toHaveLength(1);
      expect(result[0]?.results[0]?.video).toEqual(mockVideos[0]);
    });

    it('should filter out null queries', async () => {
      searchDbService.readAll.mockResolvedValue([null as any]);
      videoService.getVideos.mockResolvedValue([]);

      const result = await service.getQueries();

      expect(result).toHaveLength(0);
    });

    it('should handle queries with no results', async () => {
      const mockQueries: SearchEntity[] = [
        {
          queryId: 'query-1',
          query: 'test query',
          watch: false,
          queryStatus: SearchQueryStatus.IDLE,
          tags: [],
          results: [],
          createdAt: '2025-01-01T00:00:00.000Z',
          updatedAt: '2025-01-01T00:00:00.000Z',
        },
      ];

      searchDbService.readAll.mockResolvedValue(mockQueries);
      videoService.getVideos.mockResolvedValue([]);

      const result = await service.getQueries();

      expect(result).toHaveLength(1);
      expect(result[0]?.results).toEqual([]);
    });
  });

  describe('newQuery', () => {
    it('should create a new query and emit RUN_QUERY event', async () => {
      const query = 'test query';
      const tags = ['tag1', 'tag2'];
      const mockCreatedQuery = { queryId: 'new-query-id' } as SearchEntity;

      searchDbService.create.mockResolvedValue(mockCreatedQuery);

      const result = await service.newQuery(query, tags);

      expect(searchDbService.create).toHaveBeenCalledWith(
        expect.objectContaining({
          queryId: expect.any(String),
          query,
          watch: false,
          results: [],
          tags,
          timeFilter: null,
          queryStatus: SearchQueryStatus.RUNNING,
          createdAt: expect.any(String),
          updatedAt: expect.any(String),
        }),
      );
      expect(eventEmitter.emit).toHaveBeenCalledWith(
        SearchEvents.RUN_QUERY,
        mockCreatedQuery.queryId,
      );
      expect(result).toEqual(expect.objectContaining(mockCreatedQuery));
    });

    it('should create query with default empty tags', async () => {
      const query = 'test query';
      const mockCreatedQuery = { queryId: 'new-query-id' } as SearchEntity;

      searchDbService.create.mockResolvedValue(mockCreatedQuery);

      await service.newQuery(query);

      expect(searchDbService.create).toHaveBeenCalledWith(
        expect.objectContaining({
          tags: [],
        }),
      );
    });
  });

  describe('addToWatch', () => {
    it('should add query to watch list', async () => {
      const queryId = 'test-query-id';
      searchDbService.updateWatch.mockResolvedValue({} as SearchEntity);

      await service.addToWatch(queryId);

      expect(searchDbService.updateWatch).toHaveBeenCalledWith(queryId, true);
    });
  });

  describe('removeFromWatch', () => {
    it('should remove query from watch list', async () => {
      const queryId = 'test-query-id';
      searchDbService.updateWatch.mockResolvedValue({} as SearchEntity);

      await service.removeFromWatch(queryId);

      expect(searchDbService.updateWatch).toHaveBeenCalledWith(queryId, false);
    });
  });

  describe('reRunQuery', () => {
    it('should throw error when query not found', async () => {
      const queryId = 'non-existent-id';
      searchDbService.read.mockResolvedValue(null);

      await expect(service.reRunQuery(queryId)).rejects.toThrow(
        `Query with ID ${queryId} not found`,
      );
    });

    it('should successfully rerun query and update results', async () => {
      const queryId = 'test-query-id';
      const mockQuery = {
        queryId,
        query: 'test query',
        tags: ['tag1'],
      } as SearchEntity;

      const mockUpdatedQuery = {
        ...mockQuery,
        queryStatus: SearchQueryStatus.RUNNING,
      };
      const mockSearchResults = {
        results: [
          {
            query_id: queryId,
            results: [
              {
                id: 'result-1',
                page_content: 'content',
                type: 'test',
                metadata: {} as any,
              },
            ],
          },
        ],
      };

      searchDbService.read.mockResolvedValue(mockQuery);
      searchDbService.updateQueryStatus.mockResolvedValue(mockUpdatedQuery);
      searchShimService.search.mockReturnValue(
        of({
          data: mockSearchResults,
          status: 200,
          statusText: 'OK',
          headers: {},
          config: {},
        } as any),
      );
      searchDbService.addResults.mockResolvedValue(mockUpdatedQuery);
      videoService.getVideos.mockResolvedValue([]);

      const result = await service.reRunQuery(queryId);

      expect(searchDbService.read).toHaveBeenCalledWith(queryId);
      expect(searchDbService.updateQueryStatus).toHaveBeenCalledWith(
        queryId,
        SearchQueryStatus.RUNNING,
      );
      expect(searchShimService.search).toHaveBeenCalledWith([
        {
          query: mockQuery.query,
          query_id: queryId,
          tags: mockQuery.tags,
        },
      ]);
      expect(eventEmitter.emit).toHaveBeenCalledWith(
        SocketEvent.SEARCH_UPDATE,
        expect.any(Object),
      );
      expect(result).toBeDefined();
    });

    it('should return null when no results found', async () => {
      const queryId = 'test-query-id';
      const mockQuery = {
        queryId,
        query: 'test query',
        tags: [],
        watch: false,
        queryStatus: SearchQueryStatus.IDLE,
        results: [],
        createdAt: '2025-01-01T00:00:00.000Z',
        updatedAt: '2025-01-01T00:00:00.000Z',
      } as SearchEntity;

      searchDbService.read.mockResolvedValue(mockQuery);
      searchDbService.updateQueryStatus.mockResolvedValue(mockQuery);
      searchShimService.search.mockReturnValue(
        of({
          data: { results: [] },
          status: 200,
          statusText: 'OK',
          headers: {},
          config: {},
        } as any),
      );
      videoService.getVideos.mockResolvedValue([]);

      const result = await service.reRunQuery(queryId);

      expect(result).toBeNull();
    });

    it('should handle search errors and update query status to ERROR', async () => {
      const queryId = 'test-query-id';
      const mockQuery = {
        queryId,
        query: 'test query',
        tags: [],
        watch: false,
        queryStatus: SearchQueryStatus.IDLE,
        results: [],
        createdAt: '2025-01-01T00:00:00.000Z',
        updatedAt: '2025-01-01T00:00:00.000Z',
      } as SearchEntity;

      searchDbService.read.mockResolvedValue(mockQuery);
      searchDbService.updateQueryStatus.mockResolvedValue(mockQuery);
      searchShimService.search.mockReturnValue(
        throwError(() => new Error('Search failed')),
      );
      searchDbService.updateQueryStatusWithError.mockResolvedValue(mockQuery);
      videoService.getVideos.mockResolvedValue([]);

      const result = await service.reRunQuery(queryId);

      expect(searchDbService.updateQueryStatusWithError).toHaveBeenCalledWith(
        queryId,
        SearchQueryStatus.ERROR,
        'No videos found in search database. Please upload relevant videos before running queries.',
      );
      expect(result).toBeNull();
    });

    it('should return null when no relevant results found', async () => {
      const queryId = 'test-query-id';
      const mockQuery = {
        queryId,
        query: 'test query',
        tags: [],
        watch: false,
        queryStatus: SearchQueryStatus.IDLE,
        results: [],
        createdAt: '2025-01-01T00:00:00.000Z',
        updatedAt: '2025-01-01T00:00:00.000Z',
      } as SearchEntity;

      const mockSearchResults = {
        results: [
          {
            query_id: 'different-query-id',
            results: [],
          },
        ],
      };

      searchDbService.read.mockResolvedValue(mockQuery);
      searchDbService.updateQueryStatus.mockResolvedValue(mockQuery);
      searchShimService.search.mockReturnValue(
        of({
          data: mockSearchResults,
          status: 200,
          statusText: 'OK',
          headers: {},
          config: {},
        } as any),
      );
      videoService.getVideos.mockResolvedValue([]);

      const result = await service.reRunQuery(queryId);

      expect(result).toBeNull();
    });
  });

  describe('runSearch', () => {
    it('should run search and return results', async () => {
      const queryId = 'test-query-id';
      const query = 'test query';
      const tags = ['tag1'];
      const mockResults = { results: [] };

      searchShimService.search.mockReturnValue(
        of({
          data: mockResults,
          status: 200,
          statusText: 'OK',
          headers: {},
          config: {},
        } as any),
      );

      const result = await service.runSearch(queryId, query, tags);

      expect(searchShimService.search).toHaveBeenCalledWith([
        {
          query,
          query_id: queryId,
          tags,
        },
      ]);
      expect(result).toEqual(mockResults);
    });

    it('should return default results when data is null', async () => {
      const queryId = 'test-query-id';
      const query = 'test query';
      const tags = ['tag1'];

      searchShimService.search.mockReturnValue(
        of({
          data: null,
          status: 200,
          statusText: 'OK',
          headers: {},
          config: {},
        } as any),
      );

      const result = await service.runSearch(queryId, query, tags);

      expect(result).toEqual({ results: [] });
    });
  });

  describe('updateResults', () => {
    it('should update results and emit events', async () => {
      const queryId = 'test-query-id';
      const resultsBody: SearchResultBody = {
        query_id: queryId,
        results: [
          {
            id: 'result-1',
            page_content: 'content',
            type: 'test',
            metadata: {} as any,
          },
        ],
      };

      const mockUpdatedQuery = {
        queryId,
        queryStatus: SearchQueryStatus.IDLE,
      } as SearchEntity;

      searchDbService.addResults.mockResolvedValue(mockUpdatedQuery);
      searchDbService.updateQueryStatus.mockResolvedValue(mockUpdatedQuery);
      videoService.getVideos.mockResolvedValue([]);

      const result = await service.updateResults(queryId, resultsBody);

      expect(searchDbService.addResults).toHaveBeenCalledWith(
        queryId,
        resultsBody.results,
      );
      expect(searchDbService.updateQueryStatus).toHaveBeenCalledWith(
        queryId,
        SearchQueryStatus.IDLE,
      );
      expect(eventEmitter.emit).toHaveBeenCalledWith(
        SocketEvent.SEARCH_UPDATE,
        expect.any(Object),
      );
      expect(result).toEqual(expect.objectContaining(mockUpdatedQuery));
    });

    it('should return null when addResults returns null', async () => {
      const queryId = 'test-query-id';
      const resultsBody: SearchResultBody = {
        query_id: queryId,
        results: [],
      };

      searchDbService.addResults.mockResolvedValue(null);

      const result = await service.updateResults(queryId, resultsBody);

      expect(result).toBeNull();
    });
  });

  describe('refreshQueries', () => {
    const watchedEntity = (
      overrides: Partial<SearchEntity> = {},
    ): SearchEntity =>
      ({
        queryId: 'query-1',
        query: 'test query 1',
        watch: true,
        tags: [],
        queryStatus: SearchQueryStatus.IDLE,
        results: [],
        createdAt: '2025-01-01T00:00:00.000Z',
        updatedAt: '2025-01-01T00:00:00.000Z',
        ...overrides,
      }) as SearchEntity;

    const resultFor = (videoId: string, score: number) =>
      ({
        id: videoId,
        page_content: 'content',
        type: 'Document',
        metadata: {
          id: `${videoId}-0`,
          video_id: videoId,
          interval_num: 0,
          relevance_score: score,
        },
      }) as any;

    it('should batch all queries into a single search call', async () => {
      searchDbService.read.mockImplementation(async (queryId: string) =>
        watchedEntity({ queryId, query: `query for ${queryId}` }),
      );
      searchShimService.search.mockReturnValue(
        of({
          data: {
            results: [
              { query_id: 'query-1', results: [] },
              { query_id: 'query-2', results: [] },
            ],
          },
        } as any),
      );
      searchDbService.addResults.mockImplementation(async (queryId: string) =>
        watchedEntity({ queryId }),
      );

      const summary = await service.refreshQueries(['query-1', 'query-2']);

      expect(searchShimService.search).toHaveBeenCalledTimes(1);
      expect(searchShimService.search).toHaveBeenCalledWith([
        expect.objectContaining({ query_id: 'query-1' }),
        expect.objectContaining({ query_id: 'query-2' }),
      ]);
      expect(summary.refreshed).toBe(2);
    });

    it('should skip persistence and socket emission when results are unchanged', async () => {
      const results = [resultFor('video-1', 0.5)];
      const fingerprint = service.buildResultsFingerprint(results);

      searchDbService.read.mockResolvedValue(
        watchedEntity({ resultsFingerprint: fingerprint }),
      );
      searchShimService.search.mockReturnValue(
        of({ data: { results: [{ query_id: 'query-1', results }] } } as any),
      );

      const summary = await service.refreshQueries(['query-1']);

      expect(summary).toEqual({ refreshed: 1, changed: 0 });
      expect(searchDbService.addResults).not.toHaveBeenCalled();
      expect(searchDbService.markRefreshed).toHaveBeenCalledWith('query-1');
      expect(eventEmitter.emit).not.toHaveBeenCalledWith(
        SocketEvent.SEARCH_UPDATE,
        expect.anything(),
      );
      expect(eventEmitter.emit).not.toHaveBeenCalledWith(
        SocketEvent.SEARCH_NOTIFICATION,
      );
    });

    it('should persist and emit when results changed', async () => {
      const results = [resultFor('video-1', 0.5)];

      searchDbService.read.mockResolvedValue(
        watchedEntity({ resultsFingerprint: 'stale-fingerprint' }),
      );
      searchShimService.search.mockReturnValue(
        of({ data: { results: [{ query_id: 'query-1', results }] } } as any),
      );
      searchDbService.addResults.mockResolvedValue(watchedEntity({ results }));

      const summary = await service.refreshQueries(['query-1']);

      expect(summary).toEqual({ refreshed: 1, changed: 1 });
      expect(searchDbService.addResults).toHaveBeenCalledWith(
        'query-1',
        results,
      );
      expect(searchDbService.markRefreshed).toHaveBeenCalledWith(
        'query-1',
        service.buildResultsFingerprint(results),
      );
      expect(eventEmitter.emit).toHaveBeenCalledWith(
        SocketEvent.SEARCH_UPDATE,
        expect.anything(),
      );
      expect(eventEmitter.emit).toHaveBeenCalledWith(
        SocketEvent.SEARCH_NOTIFICATION,
      );
    });

    it('should re-normalize relative time filters against the current clock', async () => {
      searchDbService.read.mockResolvedValue(
        watchedEntity({
          timeFilterValue: 5,
          timeFilterUnit: 'minutes',
          timeFilterStart: '2020-01-01T00:00:00.000Z',
          timeFilterEnd: '2020-01-01T00:05:00.000Z',
        }),
      );
      searchShimService.search.mockReturnValue(
        of({
          data: { results: [{ query_id: 'query-1', results: [] }] },
        } as any),
      );
      searchDbService.addResults.mockResolvedValue(watchedEntity());

      await service.refreshQueries(['query-1']);

      const sentQuery = searchShimService.search.mock.calls[0][0][0];
      expect(sentQuery.time_filter).toBeDefined();
      const end = new Date(sentQuery.time_filter!.end).getTime();
      const start = new Date(sentQuery.time_filter!.start).getTime();
      expect(end - start).toBe(5 * 60 * 1000);
      expect(Date.now() - end).toBeLessThan(60 * 1000);
      expect(searchDbService.update).toHaveBeenCalledWith(
        'query-1',
        expect.objectContaining({
          timeFilter: expect.objectContaining({ source: 'relative' }),
        }),
      );
    });

    it('should leave absolute time filters untouched', async () => {
      searchDbService.read.mockResolvedValue(
        watchedEntity({
          timeFilterStart: '2020-01-01T00:00:00.000Z',
          timeFilterEnd: '2020-01-02T00:00:00.000Z',
        }),
      );
      searchShimService.search.mockReturnValue(
        of({
          data: { results: [{ query_id: 'query-1', results: [] }] },
        } as any),
      );
      searchDbService.addResults.mockResolvedValue(watchedEntity());

      await service.refreshQueries(['query-1']);

      const sentQuery = searchShimService.search.mock.calls[0][0][0];
      expect(sentQuery.time_filter).toEqual({
        start: '2020-01-01T00:00:00.000Z',
        end: '2020-01-02T00:00:00.000Z',
      });
      expect(searchDbService.update).not.toHaveBeenCalled();
    });

    it('should not wipe existing results when the search service fails', async () => {
      searchDbService.read.mockResolvedValue(watchedEntity());
      searchShimService.search.mockReturnValue(
        throwError(() => new Error('search down')),
      );

      const summary = await service.refreshQueries(['query-1']);

      expect(summary).toEqual({ refreshed: 0, changed: 0 });
      expect(searchDbService.addResults).not.toHaveBeenCalled();
      expect(eventEmitter.emit).not.toHaveBeenCalledWith(
        SocketEvent.SEARCH_NOTIFICATION,
      );
    });

    it('should return early for an empty query list', async () => {
      const summary = await service.refreshQueries([]);

      expect(summary).toEqual({ refreshed: 0, changed: 0 });
      expect(searchShimService.search).not.toHaveBeenCalled();
    });
  });

  describe('buildResultsFingerprint', () => {
    it('should be stable for identical result sets and differ otherwise', () => {
      const results = [
        {
          id: 'a',
          page_content: '',
          type: 'Document',
          metadata: {
            id: 'a-0',
            video_id: 'a',
            interval_num: 0,
            relevance_score: 0.5,
          },
        },
      ] as any;
      const changed = [
        {
          id: 'a',
          page_content: '',
          type: 'Document',
          metadata: {
            id: 'a-0',
            video_id: 'a',
            interval_num: 0,
            relevance_score: 0.9,
          },
        },
      ] as any;

      expect(service.buildResultsFingerprint(results)).toBe(
        service.buildResultsFingerprint([...results]),
      );
      expect(service.buildResultsFingerprint(results)).not.toBe(
        service.buildResultsFingerprint(changed),
      );
      expect(service.buildResultsFingerprint([])).toBe('empty');
    });

    it('should distinguish clips of the same video (live-ingestion shape)', () => {
      // Real aggregated results carry no `id`/`interval_num`; a single live
      // stream also means every result shares one `video_id`. The clip must
      // still be identified by its position within the video.
      const clip = (timestamp: number, start: number, end: number) =>
        ({
          id: null,
          page_content: '',
          type: 'Document',
          metadata: {
            video_id: 'live-stream-1',
            timestamp,
            seek_timestamp: timestamp,
            segment_start: start,
            segment_end: end,
            relevance_score: 1,
          },
        }) as any;

      const before = [clip(1.75, 0, 8), clip(9.5, 8, 16)];
      const after = [clip(17.2, 16, 24), clip(25.1, 24, 32)];

      expect(service.buildResultsFingerprint(before)).not.toBe(
        service.buildResultsFingerprint(after),
      );
      expect(service.buildResultsFingerprint(before)).toBe(
        service.buildResultsFingerprint([clip(1.75, 0, 8), clip(9.5, 8, 16)]),
      );
      expect(service.buildResultsFingerprint(before)).not.toBe(
        service.buildResultsFingerprint([...before].reverse()),
      );
    });
  });
});
