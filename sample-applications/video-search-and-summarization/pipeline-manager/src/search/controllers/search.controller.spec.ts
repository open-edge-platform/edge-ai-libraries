// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Test, TestingModule } from '@nestjs/testing';
import { BadRequestException } from '@nestjs/common';
import { SearchController } from './search.controller';
import { SearchStateService } from '../services/search-state.service';
import { SearchDbService } from '../services/search-db.service';
import { SearchShimService } from '../services/search-shim.service';
import { of } from 'rxjs';

describe('SearchController', () => {
  let controller: SearchController;
  let searchStateService: jest.Mocked<SearchStateService>;
  let searchDbService: jest.Mocked<SearchDbService>;
  let searchShimService: jest.Mocked<SearchShimService>;

  const mockQuery = {
    queryId: 'test-query-123',
    query: 'test search query',
    tags: ['tag1', 'tag2'],
    results: []
  };

  const mockQueries = [mockQuery, { queryId: 'query2', query: 'another query', results: [] }];

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      controllers: [SearchController],
      providers: [
        {
          provide: SearchStateService,
          useValue: {
            getQueries: jest.fn().mockResolvedValue(mockQueries),
            newQuery: jest.fn().mockResolvedValue(mockQuery),
            reRunQuery: jest.fn().mockResolvedValue(mockQuery),
            addToWatch: jest.fn().mockResolvedValue(true),
            removeFromWatch: jest.fn().mockResolvedValue(true)
          }
        },
        {
          provide: SearchDbService,
          useValue: {
            readAllWatched: jest.fn().mockResolvedValue([mockQuery]),
            read: jest.fn().mockResolvedValue(mockQuery),
            remove: jest.fn().mockResolvedValue(true)
          }
        },
        {
          provide: SearchShimService,
          useValue: {
            search: jest.fn().mockReturnValue(
              of({ data: { results: [{ id: '1', content: 'test result' }] } })
            )
          }
        }
      ]
    }).compile();

    controller = module.get<SearchController>(SearchController);
    searchStateService = module.get(SearchStateService);
    searchDbService = module.get(SearchDbService);
    searchShimService = module.get(SearchShimService);
  });

  it('should be defined', () => {
    expect(controller).toBeDefined();
  });

  describe('getQueries', () => {
    it('should return all queries', async () => {
      const result = await controller.getQueries();
      
      expect(result).toEqual(mockQueries);
      expect(searchStateService.getQueries).toHaveBeenCalled();
    });
  });

  describe('getWatchedQueries', () => {
    it('should return watched queries', async () => {
      const result = await controller.getWatchedQueries();
      
      expect(result).toEqual([mockQuery]);
      expect(searchDbService.readAllWatched).toHaveBeenCalled();
    });
  });

  describe('getQuery', () => {
    it('should return a specific query by ID', async () => {
      const queryId = 'test-query-123';
      const result = await controller.getQuery({ queryId });
      
      expect(result).toEqual(mockQuery);
      expect(searchDbService.read).toHaveBeenCalledWith(queryId);
    });
  });

  describe('addQuery', () => {
    it('should add a new query without tags', async () => {
      const reqBody = {
        query: 'new test query'
      };
      
      const result = await controller.addQuery(reqBody);
      
      expect(result).toEqual(mockQuery);
      expect(searchStateService.newQuery).toHaveBeenCalledWith('new test query', []);
    });

    it('should add a new query with tags', async () => {
      const reqBody = {
        query: 'new test query',
        tags: 'tag1, tag2, tag3'
      };
      
      const result = await controller.addQuery(reqBody);
      
      expect(result).toEqual(mockQuery);
      expect(searchStateService.newQuery).toHaveBeenCalledWith('new test query', ['tag1', 'tag2', 'tag3']);
    });

    it('should handle empty tags string', async () => {
      const reqBody = {
        query: 'new test query',
        tags: ''
      };
      
      const result = await controller.addQuery(reqBody);
      
      expect(result).toEqual(mockQuery);
      expect(searchStateService.newQuery).toHaveBeenCalledWith('new test query', []);
    });

    it('should handle error when adding query', async () => {
      searchStateService.newQuery.mockRejectedValueOnce(new Error('Database error'));
      
      const reqBody = { query: 'failing query' };
      
      await expect(controller.addQuery(reqBody)).rejects.toThrow(BadRequestException);
    });
  });

  describe('refetchQuery', () => {
    it('should refetch a query by ID', async () => {
      const queryId = 'test-query-123';
      const result = await controller.refetchQuery({ queryId });
      
      expect(result).toEqual(mockQuery);
      expect(searchStateService.reRunQuery).toHaveBeenCalledWith(queryId);
    });
  });

  describe('searchQuery', () => {
    it('should perform a direct search query', async () => {
      const reqBody = { query: 'direct search query' };
      
      const result = await controller.searchQuery(reqBody);
      
      expect(result).toEqual({ results: [{ id: '1', content: 'test result' }] });
      expect(searchShimService.search).toHaveBeenCalledWith([{
        query: 'direct search query',
        query_id: expect.any(String)
      }]);
    });
  });

  describe('watchQuery', () => {
    it('should add query to watch when watch is true', async () => {
      const queryId = 'test-query-123';
      const body = { watch: true };
      
      const result = await controller.watchQuery({ queryId }, body);
      
      expect(result).toBe(true);
      expect(searchStateService.addToWatch).toHaveBeenCalledWith(queryId);
    });

    it('should remove query from watch when watch is false', async () => {
      const queryId = 'test-query-123';
      const body = { watch: false };
      
      const result = await controller.watchQuery({ queryId }, body);
      
      expect(result).toBe(true);
      expect(searchStateService.removeFromWatch).toHaveBeenCalledWith(queryId);
    });

    it('should throw BadRequestException when watch property is missing', () => {
      const queryId = 'test-query-123';
      const body = {} as any;
      
      expect(() => controller.watchQuery({ queryId }, body))
        .toThrow(BadRequestException);
    });
  });

  describe('deleteQuery', () => {
    it('should delete a query by ID', async () => {
      const queryId = 'test-query-123';
      
      const result = await controller.deleteQuery({ queryId });
      
      expect(result).toBe(true);
      expect(searchDbService.remove).toHaveBeenCalledWith(queryId);
    });
  });

  describe('error handling', () => {
    it('should handle service errors gracefully', async () => {
      searchDbService.read.mockRejectedValueOnce(new Error('Service error'));
      
      await expect(controller.getQuery({ queryId: 'failing-query' }))
        .rejects.toThrow('Service error');
    });

    it('should handle watch service errors', async () => {
      searchStateService.addToWatch.mockRejectedValueOnce(new Error('Watch error'));
      
      await expect(controller.watchQuery({ queryId: 'test' }, { watch: true }))
        .rejects.toThrow('Watch error');
    });
  });
});
