// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Test, TestingModule } from '@nestjs/testing';
import { TagsService } from './tags.service';
import { TagsDbService } from './tags-db.service';

describe('TagsService', () => {
  let service: TagsService;
  let tagsDbService: jest.Mocked<TagsDbService>;

  const mockExistingTags = [
    { dbId: 1, tag: 'existing-tag-1', createdAt: '2023-01-01', updatedAt: '2023-01-01' },
    { dbId: 2, tag: 'existing-tag-2', createdAt: '2023-01-01', updatedAt: '2023-01-01' }
  ];

  beforeEach(async () => {
    const tagsDbServiceMock = {
      create: jest.fn(),
      createMany: jest.fn(),
      readAll: jest.fn(),
      read: jest.fn(),
      remove: jest.fn(),
    };

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        TagsService,
        { provide: TagsDbService, useValue: tagsDbServiceMock },
      ],
    }).compile();

    service = module.get<TagsService>(TagsService);
    tagsDbService = module.get(TagsDbService) as jest.Mocked<TagsDbService>;
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  describe('addTags', () => {
    it('should add new tags that do not exist in database', async () => {
      const newTags = ['new-tag-1', 'new-tag-2'];
      const createdTags = [
        { dbId: 3, tag: 'new-tag-1', createdAt: '2023-01-02', updatedAt: '2023-01-02' },
        { dbId: 4, tag: 'new-tag-2', createdAt: '2023-01-02', updatedAt: '2023-01-02' }
      ];

      tagsDbService.readAll.mockResolvedValue(mockExistingTags);
      tagsDbService.createMany.mockResolvedValue(createdTags);

      const result = await service.addTags(newTags);

      expect(tagsDbService.readAll).toHaveBeenCalledTimes(1);
      expect(tagsDbService.createMany).toHaveBeenCalledWith(newTags);
      expect(result).toEqual(createdTags);
    });

    it('should filter out existing tags and only add new ones', async () => {
      const tagsToAdd = ['existing-tag-1', 'new-tag-1', 'existing-tag-2', 'new-tag-2'];
      const expectedNewTags = ['new-tag-1', 'new-tag-2'];
      const createdTags = [
        { dbId: 3, tag: 'new-tag-1', createdAt: '2023-01-02', updatedAt: '2023-01-02' },
        { dbId: 4, tag: 'new-tag-2', createdAt: '2023-01-02', updatedAt: '2023-01-02' }
      ];

      tagsDbService.readAll.mockResolvedValue(mockExistingTags);
      tagsDbService.createMany.mockResolvedValue(createdTags);

      const result = await service.addTags(tagsToAdd);

      expect(tagsDbService.readAll).toHaveBeenCalledTimes(1);
      expect(tagsDbService.createMany).toHaveBeenCalledWith(expectedNewTags);
      expect(result).toEqual(createdTags);
    });

    it('should remove duplicate tags from input before processing', async () => {
      const duplicateTags = ['new-tag-1', 'new-tag-2', 'new-tag-1', 'new-tag-2'];
      const expectedUniqueTags = ['new-tag-1', 'new-tag-2'];
      const createdTags = [
        { dbId: 3, tag: 'new-tag-1', createdAt: '2023-01-02', updatedAt: '2023-01-02' },
        { dbId: 4, tag: 'new-tag-2', createdAt: '2023-01-02', updatedAt: '2023-01-02' }
      ];

      tagsDbService.readAll.mockResolvedValue([]);
      tagsDbService.createMany.mockResolvedValue(createdTags);

      const result = await service.addTags(duplicateTags);

      expect(tagsDbService.readAll).toHaveBeenCalledTimes(1);
      expect(tagsDbService.createMany).toHaveBeenCalledWith(expectedUniqueTags);
      expect(result).toEqual(createdTags);
    });

    it('should return early when input tags array is empty', async () => {
      const result = await service.addTags([]);

      expect(tagsDbService.readAll).not.toHaveBeenCalled();
      expect(tagsDbService.createMany).not.toHaveBeenCalled();
      expect(result).toBeUndefined();
    });

    it('should return early when all tags already exist', async () => {
      const existingTagNames = ['existing-tag-1', 'existing-tag-2'];

      tagsDbService.readAll.mockResolvedValue(mockExistingTags);

      const result = await service.addTags(existingTagNames);

      expect(tagsDbService.readAll).toHaveBeenCalledTimes(1);
      expect(tagsDbService.createMany).not.toHaveBeenCalled();
      expect(result).toBeUndefined();
    });

    it('should handle empty existing tags in database', async () => {
      const newTags = ['tag-1', 'tag-2'];
      const createdTags = [
        { dbId: 1, tag: 'tag-1', createdAt: '2023-01-02', updatedAt: '2023-01-02' },
        { dbId: 2, tag: 'tag-2', createdAt: '2023-01-02', updatedAt: '2023-01-02' }
      ];

      tagsDbService.readAll.mockResolvedValue([]);
      tagsDbService.createMany.mockResolvedValue(createdTags);

      const result = await service.addTags(newTags);

      expect(tagsDbService.readAll).toHaveBeenCalledTimes(1);
      expect(tagsDbService.createMany).toHaveBeenCalledWith(newTags);
      expect(result).toEqual(createdTags);
    });

    it('should handle database errors gracefully', async () => {
      const newTags = ['new-tag-1'];
      const dbError = new Error('Database connection failed');

      tagsDbService.readAll.mockRejectedValue(dbError);

      await expect(service.addTags(newTags)).rejects.toThrow(dbError);
      expect(tagsDbService.readAll).toHaveBeenCalledTimes(1);
      expect(tagsDbService.createMany).not.toHaveBeenCalled();
    });

    it('should handle createMany errors gracefully', async () => {
      const newTags = ['new-tag-1'];
      const createError = new Error('Failed to create tags');

      tagsDbService.readAll.mockResolvedValue([]);
      tagsDbService.createMany.mockRejectedValue(createError);

      await expect(service.addTags(newTags)).rejects.toThrow(createError);
      expect(tagsDbService.readAll).toHaveBeenCalledTimes(1);
      expect(tagsDbService.createMany).toHaveBeenCalledWith(newTags);
    });
  });
});
