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
    };

    const mockVideoService = {
      getVideos: jest.fn(),
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

      expect(searchDbService.create).toHaveBeenCalledWith({
        queryId: expect.any(String),
        query,
        watch: false,
        results: [],
        tags,
        queryStatus: SearchQueryStatus.RUNNING,
        createdAt: expect.any(String),
        updatedAt: expect.any(String),
      });
      expect(eventEmitter.emit).toHaveBeenCalledWith(SearchEvents.RUN_QUERY, mockCreatedQuery.queryId);
      expect(result).toEqual(mockCreatedQuery);
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

      await expect(service.reRunQuery(queryId)).rejects.toThrow(`Query with ID ${queryId} not found`);
    });

    it('should successfully rerun query and update results', async () => {
      const queryId = 'test-query-id';
      const mockQuery = {
        queryId,
        query: 'test query',
        tags: ['tag1'],
      } as SearchEntity;

      const mockUpdatedQuery = { ...mockQuery, queryStatus: SearchQueryStatus.RUNNING };
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
      searchShimService.search.mockReturnValue(of({ 
        data: mockSearchResults,
        status: 200,
        statusText: 'OK',
        headers: {},
        config: {},
      } as any));
      searchDbService.addResults.mockResolvedValue(mockUpdatedQuery);
      videoService.getVideos.mockResolvedValue([]);

      const result = await service.reRunQuery(queryId);

      expect(searchDbService.read).toHaveBeenCalledWith(queryId);
      expect(searchDbService.updateQueryStatus).toHaveBeenCalledWith(queryId, SearchQueryStatus.RUNNING);
      expect(searchShimService.search).toHaveBeenCalledWith([
        {
          query: mockQuery.query,
          query_id: queryId,
          tags: mockQuery.tags,
        },
      ]);
      expect(eventEmitter.emit).toHaveBeenCalledWith(SocketEvent.SEARCH_UPDATE, expect.any(Object));
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
      searchShimService.search.mockReturnValue(of({ 
        data: { results: [] },
        status: 200,
        statusText: 'OK',
        headers: {},
        config: {},
      } as any));
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
      searchShimService.search.mockReturnValue(of({ 
        data: mockSearchResults,
        status: 200,
        statusText: 'OK',
        headers: {},
        config: {},
      } as any));
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

      searchShimService.search.mockReturnValue(of({ 
        data: mockResults,
        status: 200,
        statusText: 'OK',
        headers: {},
        config: {},
      } as any));

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

      searchShimService.search.mockReturnValue(of({ 
        data: null,
        status: 200,
        statusText: 'OK',
        headers: {},
        config: {},
      } as any));

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

      expect(searchDbService.addResults).toHaveBeenCalledWith(queryId, resultsBody.results);
      expect(searchDbService.updateQueryStatus).toHaveBeenCalledWith(queryId, SearchQueryStatus.IDLE);
      expect(eventEmitter.emit).toHaveBeenCalledWith(SocketEvent.SEARCH_UPDATE, expect.any(Object));
      expect(result).toEqual(mockUpdatedQuery);
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

  describe('syncSearches', () => {
    it('should sync watched queries and emit notification', async () => {
      const mockWatchedQueries = [
        {
          queryId: 'query-1',
          query: 'test query 1',
          watch: true,
          tags: [],
          queryStatus: SearchQueryStatus.IDLE,
          results: [],
          createdAt: '2025-01-01T00:00:00.000Z',
          updatedAt: '2025-01-01T00:00:00.000Z',
        },
        {
          queryId: 'query-2',
          query: 'test query 2',
          watch: true,
          tags: [],
          queryStatus: SearchQueryStatus.IDLE,
          results: [],
          createdAt: '2025-01-01T00:00:00.000Z',
          updatedAt: '2025-01-01T00:00:00.000Z',
        },
      ] as SearchEntity[];

      searchDbService.readAll.mockResolvedValue(mockWatchedQueries);
      jest.spyOn(service, 'reRunQuery').mockResolvedValue({} as SearchEntity);

      await service.syncSearches();

      expect(searchDbService.readAll).toHaveBeenCalled();
      expect(service.reRunQuery).toHaveBeenCalledTimes(2);
      expect(service.reRunQuery).toHaveBeenCalledWith('query-1');
      expect(service.reRunQuery).toHaveBeenCalledWith('query-2');
      expect(eventEmitter.emit).toHaveBeenCalledWith(SocketEvent.SEARCH_NOTIFICATION);
    });

    it('should not emit notification when no watched queries', async () => {
      const mockQueries = [
        {
          queryId: 'query-1',
          query: 'test query 1',
          watch: false,
          tags: [],
          queryStatus: SearchQueryStatus.IDLE,
          results: [],
          createdAt: '2025-01-01T00:00:00.000Z',
          updatedAt: '2025-01-01T00:00:00.000Z',
        },
      ] as SearchEntity[];

      searchDbService.readAll.mockResolvedValue(mockQueries);

      await service.syncSearches();

      expect(eventEmitter.emit).not.toHaveBeenCalledWith(SocketEvent.SEARCH_NOTIFICATION);
    });
  });
});
