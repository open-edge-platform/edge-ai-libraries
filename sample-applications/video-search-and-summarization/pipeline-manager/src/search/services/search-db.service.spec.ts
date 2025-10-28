// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Test, TestingModule } from '@nestjs/testing';
import { SearchDbService } from './search-db.service';
import { getRepositoryToken } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { SearchEntity } from '../model/search.entity';
import { SearchQuery, SearchQueryStatus, SearchResult } from '../model/search.model';

describe('SearchDbService', () => {
  let service: SearchDbService;
  let repository: jest.Mocked<Repository<SearchEntity>>;

  beforeEach(async () => {
    const repositoryMock = {
      create: jest.fn(),
      save: jest.fn(),
      find: jest.fn(),
      findOne: jest.fn(),
      remove: jest.fn(),
      update: jest.fn(),
      delete: jest.fn(),
    };

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        SearchDbService,
        {
          provide: getRepositoryToken(SearchEntity),
          useValue: repositoryMock,
        },
      ],
    }).compile();

    service = module.get<SearchDbService>(SearchDbService);
    repository = module.get(getRepositoryToken(SearchEntity)) as jest.Mocked<Repository<SearchEntity>>;
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  describe('create', () => {
    it('should create a new search entity', async () => {
      const mockSearch: SearchQuery = {
        queryId: 'test-query-id',
        query: 'test query',
        watch: false,
        results: [],
        tags: [],
        queryStatus: SearchQueryStatus.RUNNING,
        createdAt: '2025-01-01T00:00:00.000Z',
        updatedAt: '2025-01-01T00:00:00.000Z',
      };

      const mockCreatedEntity = { id: 1, ...mockSearch };
      const mockSavedEntity = { id: 1, ...mockSearch };

      repository.create.mockReturnValue(mockCreatedEntity as SearchEntity);
      repository.save.mockResolvedValue(mockSavedEntity as SearchEntity);

      const result = await service.create(mockSearch);

      expect(repository.create).toHaveBeenCalledWith({
        ...mockSearch,
        createdAt: expect.any(String),
        updatedAt: expect.any(String),
      });
      expect(repository.save).toHaveBeenCalledWith(mockCreatedEntity);
      expect(result).toEqual(mockSavedEntity);
    });
  });

  describe('updateQueryStatus', () => {
    it('should update query status and clear error message for non-error status', async () => {
      const queryId = 'test-query-id';
      const status = SearchQueryStatus.IDLE;
      const mockSearch = {
        queryId,
        queryStatus: SearchQueryStatus.ERROR,
        errorMessage: 'Previous error',
      } as SearchEntity;

      jest.spyOn(service, 'read').mockResolvedValue(mockSearch);
      repository.save.mockResolvedValue({ ...mockSearch, queryStatus: status } as SearchEntity);

      const result = await service.updateQueryStatus(queryId, status);

      expect(service.read).toHaveBeenCalledWith(queryId);
      expect(mockSearch.queryStatus).toBe(status);
      expect(mockSearch.errorMessage).toBeUndefined();
      expect(mockSearch.updatedAt).toBeDefined();
      expect(repository.save).toHaveBeenCalledWith(mockSearch);
      expect(result).toBeDefined();
    });

    it('should return null when search not found', async () => {
      const queryId = 'non-existent-id';
      jest.spyOn(service, 'read').mockResolvedValue(null);

      const result = await service.updateQueryStatus(queryId, SearchQueryStatus.IDLE);

      expect(result).toBeNull();
    });

    it('should not clear error message for error status', async () => {
      const queryId = 'test-query-id';
      const status = SearchQueryStatus.ERROR;
      const mockSearch = {
        queryId,
        queryStatus: SearchQueryStatus.RUNNING,
        errorMessage: 'Existing error',
      } as SearchEntity;

      jest.spyOn(service, 'read').mockResolvedValue(mockSearch);
      repository.save.mockResolvedValue({ ...mockSearch, queryStatus: status } as SearchEntity);

      await service.updateQueryStatus(queryId, status);

      expect(mockSearch.errorMessage).toBe('Existing error');
    });
  });

  describe('updateQueryStatusWithError', () => {
    it('should update query status with error message', async () => {
      const queryId = 'test-query-id';
      const status = SearchQueryStatus.ERROR;
      const errorMessage = 'Test error message';
      const mockSearch = {
        queryId,
        queryStatus: SearchQueryStatus.RUNNING,
      } as SearchEntity;

      jest.spyOn(service, 'read').mockResolvedValue(mockSearch);
      repository.save.mockResolvedValue({ ...mockSearch, queryStatus: status, errorMessage } as SearchEntity);

      const result = await service.updateQueryStatusWithError(queryId, status, errorMessage);

      expect(service.read).toHaveBeenCalledWith(queryId);
      expect(mockSearch.queryStatus).toBe(status);
      expect(mockSearch.errorMessage).toBe(errorMessage);
      expect(mockSearch.updatedAt).toBeDefined();
      expect(repository.save).toHaveBeenCalledWith(mockSearch);
      expect(result).toBeDefined();
    });

    it('should return null when search not found', async () => {
      const queryId = 'non-existent-id';
      jest.spyOn(service, 'read').mockResolvedValue(null);

      const result = await service.updateQueryStatusWithError(queryId, SearchQueryStatus.ERROR, 'Error message');

      expect(result).toBeNull();
    });
  });

  describe('readAll', () => {
    it('should return all search entities', async () => {
      const mockSearches = [
        { queryId: 'query-1', query: 'test 1' },
        { queryId: 'query-2', query: 'test 2' },
      ] as SearchEntity[];

      repository.find.mockResolvedValue(mockSearches);

      const result = await service.readAll();

      expect(repository.find).toHaveBeenCalled();
      expect(result).toEqual(mockSearches);
    });

    it('should return empty array when no searches found', async () => {
      repository.find.mockResolvedValue(null as any);

      const result = await service.readAll();

      expect(result).toEqual([]);
    });
  });

  describe('readAllWatched', () => {
    it('should return all watched search entities', async () => {
      const mockWatchedSearches = [
        { queryId: 'query-1', query: 'test 1', watch: true },
      ] as SearchEntity[];

      repository.find.mockResolvedValue(mockWatchedSearches);

      const result = await service.readAllWatched();

      expect(repository.find).toHaveBeenCalledWith({
        where: { watch: true },
      });
      expect(result).toEqual(mockWatchedSearches);
    });

    it('should return empty array when no watched searches found', async () => {
      repository.find.mockResolvedValue(null as any);

      const result = await service.readAllWatched();

      expect(result).toEqual([]);
    });
  });

  describe('read', () => {
    it('should return search entity by queryId', async () => {
      const queryId = 'test-query-id';
      const mockSearch = { queryId, query: 'test query' } as SearchEntity;

      repository.findOne.mockResolvedValue(mockSearch);

      const result = await service.read(queryId);

      expect(repository.findOne).toHaveBeenCalledWith({
        where: { queryId },
      });
      expect(result).toEqual(mockSearch);
    });

    it('should return null when search not found', async () => {
      const queryId = 'non-existent-id';
      repository.findOne.mockResolvedValue(null);

      const result = await service.read(queryId);

      expect(result).toBeNull();
    });
  });

  describe('addResults', () => {
    it('should add results to existing search', async () => {
      const queryId = 'test-query-id';
      const mockResults: SearchResult[] = [
        { 
          id: 'result-1', 
          page_content: 'test content',
          type: 'test',
          metadata: {
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
            video_id: 'video-1',
            video_path: '/test/path',
            video_rel_url: '/rel/path',
            video_remote_path: '/remote/path',
            video_url: 'http://test.com/video',
            year: 2025,
            relevance_score: 0.95
          }
        },
      ];
      const mockSearch = {
        queryId,
        query: 'test query',
        watch: false,
        results: [],
        queryStatus: SearchQueryStatus.RUNNING,
        tags: [],
        createdAt: '2025-01-01T00:00:00.000Z',
        updatedAt: '2025-01-01T00:00:00.000Z',
      } as SearchEntity;

      jest.spyOn(service, 'read').mockResolvedValue(mockSearch);
      repository.save.mockResolvedValue({ ...mockSearch, results: mockResults } as SearchEntity);

      const result = await service.addResults(queryId, mockResults);

      expect(service.read).toHaveBeenCalledWith(queryId);
      expect(mockSearch.results).toEqual(mockResults);
      expect(mockSearch.queryStatus).toBe(SearchQueryStatus.IDLE);
      expect(mockSearch.updatedAt).toBeDefined();
      expect(repository.save).toHaveBeenCalledWith(mockSearch);
      expect(result).toBeDefined();
    });

    it('should return null when search not found', async () => {
      const queryId = 'non-existent-id';
      const mockResults: SearchResult[] = [];

      jest.spyOn(service, 'read').mockResolvedValue(null);

      const result = await service.addResults(queryId, mockResults);

      expect(result).toBeNull();
    });
  });

  describe('updateWatch', () => {
    it('should update watch status', async () => {
      const queryId = 'test-query-id';
      const watch = true;
      const mockSearch = {
        queryId,
        watch: false,
      } as SearchEntity;

      jest.spyOn(service, 'read').mockResolvedValue(mockSearch);
      repository.save.mockResolvedValue({ ...mockSearch, watch } as SearchEntity);

      const result = await service.updateWatch(queryId, watch);

      expect(service.read).toHaveBeenCalledWith(queryId);
      expect(mockSearch.watch).toBe(watch);
      expect(mockSearch.updatedAt).toBeDefined();
      expect(repository.save).toHaveBeenCalledWith(mockSearch);
      expect(result).toBeDefined();
    });

    it('should return null when search not found', async () => {
      const queryId = 'non-existent-id';
      jest.spyOn(service, 'read').mockResolvedValue(null);

      const result = await service.updateWatch(queryId, true);

      expect(result).toBeNull();
    });
  });

  describe('update', () => {
    it('should update search with partial data', async () => {
      const queryId = 'test-query-id';
      const partialUpdate = { query: 'updated query', tags: ['new-tag'] };
      const mockSearch = {
        queryId,
        query: 'original query',
        watch: false,
        tags: [],
        queryStatus: SearchQueryStatus.IDLE,
        results: [],
        createdAt: '2025-01-01T00:00:00.000Z',
        updatedAt: '2025-01-01T00:00:00.000Z',
      } as SearchEntity;

      jest.spyOn(service, 'read').mockResolvedValue(mockSearch);
      repository.save.mockResolvedValue({ ...mockSearch, ...partialUpdate } as SearchEntity);

      const result = await service.update(queryId, partialUpdate);

      expect(service.read).toHaveBeenCalledWith(queryId);
      expect(repository.save).toHaveBeenCalledWith({
        ...mockSearch,
        ...partialUpdate,
        updatedAt: expect.any(String),
      });
      expect(result).toBeDefined();
    });

    it('should return null when search not found', async () => {
      const queryId = 'non-existent-id';
      jest.spyOn(service, 'read').mockResolvedValue(null);

      const result = await service.update(queryId, { query: 'updated' });

      expect(result).toBeNull();
    });
  });

  describe('remove', () => {
    it('should remove existing search', async () => {
      const queryId = 'test-query-id';
      const mockSearch = { queryId, query: 'test query' } as SearchEntity;

      jest.spyOn(service, 'read').mockResolvedValue(mockSearch);
      repository.remove.mockResolvedValue(mockSearch);

      await service.remove(queryId);

      expect(service.read).toHaveBeenCalledWith(queryId);
      expect(repository.remove).toHaveBeenCalledWith(mockSearch);
    });

    it('should return early when search not found', async () => {
      const queryId = 'non-existent-id';
      jest.spyOn(service, 'read').mockResolvedValue(null);

      await service.remove(queryId);

      expect(service.read).toHaveBeenCalledWith(queryId);
      expect(repository.remove).not.toHaveBeenCalled();
    });
  });
});
