// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Test, TestingModule } from '@nestjs/testing';
import { TagsDbService } from './tags-db.service';
import { getRepositoryToken } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { TagEntity } from '../models/tags.entity';
import { Logger } from '@nestjs/common';

describe('TagsDbService', () => {
  let service: TagsDbService;
  let repository: jest.Mocked<Repository<TagEntity>>;

  const mockTagEntity: TagEntity = {
    dbId: 1,
    tag: 'test-tag',
    createdAt: '2025-01-01T00:00:00.000Z',
  };

  beforeEach(async () => {
    const repositoryMock = {
      create: jest.fn(),
      save: jest.fn(),
      find: jest.fn(),
      findOne: jest.fn(),
      update: jest.fn(),
      delete: jest.fn(),
      remove: jest.fn(),
    };

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        TagsDbService,
        {
          provide: getRepositoryToken(TagEntity),
          useValue: repositoryMock,
        },
      ],
    }).compile();

    service = module.get<TagsDbService>(TagsDbService);
    repository = module.get(getRepositoryToken(TagEntity)) as jest.Mocked<Repository<TagEntity>>;

    // Reset mocks
    jest.clearAllMocks();
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  describe('create', () => {
    it('should create and save a new tag', async () => {
      const tagName = 'new-tag';
      const logSpy = jest.spyOn(Logger, 'log').mockImplementation();

      repository.create.mockReturnValue(mockTagEntity);
      repository.save.mockResolvedValue(mockTagEntity);

      const result = await service.create(tagName);

      expect(repository.create).toHaveBeenCalledWith({ tag: tagName });
      expect(repository.save).toHaveBeenCalledWith(mockTagEntity);
      expect(logSpy).toHaveBeenCalledWith('Adding tag to database', tagName);
      expect(result).toEqual(mockTagEntity);

      logSpy.mockRestore();
    });

    it('should handle repository errors during creation', async () => {
      const tagName = 'error-tag';
      const logSpy = jest.spyOn(Logger, 'log').mockImplementation();

      repository.create.mockReturnValue(mockTagEntity);
      repository.save.mockRejectedValue(new Error('Database error'));

      await expect(service.create(tagName)).rejects.toThrow('Database error');

      expect(repository.create).toHaveBeenCalledWith({ tag: tagName });
      expect(repository.save).toHaveBeenCalledWith(mockTagEntity);
      expect(logSpy).toHaveBeenCalledWith('Adding tag to database', tagName);

      logSpy.mockRestore();
    });
  });

  describe('createMany', () => {
    it('should create and save multiple tags', async () => {
      const tags = ['tag1', 'tag2', 'tag3'];
      const mockTags = tags.map((tag, index) => ({
        dbId: index + 1,
        tag,
        createdAt: '2025-01-01T00:00:00.000Z',
      }));
      const logSpy = jest.spyOn(Logger, 'log').mockImplementation();

      repository.create.mockImplementation((data: { tag: string }) => ({
        ...mockTagEntity,
        tag: data.tag,
      }));
      repository.save.mockResolvedValue(mockTags as any);

      const result = await service.createMany(tags);

      expect(repository.create).toHaveBeenCalledTimes(3);
      expect(repository.create).toHaveBeenCalledWith({ tag: 'tag1' });
      expect(repository.create).toHaveBeenCalledWith({ tag: 'tag2' });
      expect(repository.create).toHaveBeenCalledWith({ tag: 'tag3' });
      expect(repository.save).toHaveBeenCalledWith([
        { ...mockTagEntity, tag: 'tag1' },
        { ...mockTagEntity, tag: 'tag2' },
        { ...mockTagEntity, tag: 'tag3' },
      ]);
      expect(logSpy).toHaveBeenCalledWith('Adding multiple tags to database', tags);
      expect(result).toEqual(mockTags);

      logSpy.mockRestore();
    });

    it('should handle empty tags array', async () => {
      const tags: string[] = [];
      const logSpy = jest.spyOn(Logger, 'log').mockImplementation();

      repository.save.mockResolvedValue([] as any);

      const result = await service.createMany(tags);

      expect(repository.create).not.toHaveBeenCalled();
      expect(repository.save).toHaveBeenCalledWith([]);
      expect(logSpy).toHaveBeenCalledWith('Adding multiple tags to database', tags);
      expect(result).toEqual([]);

      logSpy.mockRestore();
    });

    it('should handle repository errors during bulk creation', async () => {
      const tags = ['tag1', 'tag2'];
      const logSpy = jest.spyOn(Logger, 'log').mockImplementation();

      repository.create.mockReturnValue(mockTagEntity);
      repository.save.mockRejectedValue(new Error('Bulk insert error'));

      await expect(service.createMany(tags)).rejects.toThrow('Bulk insert error');

      expect(repository.create).toHaveBeenCalledTimes(2);
      expect(logSpy).toHaveBeenCalledWith('Adding multiple tags to database', tags);

      logSpy.mockRestore();
    });
  });

  describe('readAll', () => {
    it('should return all tags', async () => {
      const mockTags = [
        mockTagEntity,
        { dbId: 2, tag: 'tag2', createdAt: '2025-01-01T00:00:00.000Z' },
        { dbId: 3, tag: 'tag3', createdAt: '2025-01-01T00:00:00.000Z' },
      ];

      repository.find.mockResolvedValue(mockTags);

      const result = await service.readAll();

      expect(repository.find).toHaveBeenCalled();
      expect(result).toEqual(mockTags);
    });

    it('should return empty array when no tags exist', async () => {
      repository.find.mockResolvedValue([]);

      const result = await service.readAll();

      expect(repository.find).toHaveBeenCalled();
      expect(result).toEqual([]);
    });

    it('should handle repository errors during read all', async () => {
      repository.find.mockRejectedValue(new Error('Database connection error'));

      await expect(service.readAll()).rejects.toThrow('Database connection error');

      expect(repository.find).toHaveBeenCalled();
    });
  });

  describe('read', () => {
    it('should return tag by id', async () => {
      const tagId = 1;

      repository.findOne.mockResolvedValue(mockTagEntity);

      const result = await service.read(tagId);

      expect(repository.findOne).toHaveBeenCalledWith({
        where: { dbId: tagId },
      });
      expect(result).toEqual(mockTagEntity);
    });

    it('should return null when tag not found', async () => {
      const tagId = 999;

      repository.findOne.mockResolvedValue(null);

      const result = await service.read(tagId);

      expect(repository.findOne).toHaveBeenCalledWith({
        where: { dbId: tagId },
      });
      expect(result).toBeNull();
    });

    it('should handle undefined response from repository', async () => {
      const tagId = 1;

      repository.findOne.mockResolvedValue(undefined as any);

      const result = await service.read(tagId);

      expect(repository.findOne).toHaveBeenCalledWith({
        where: { dbId: tagId },
      });
      expect(result).toBeNull();
    });

    it('should handle repository errors during read', async () => {
      const tagId = 1;

      repository.findOne.mockRejectedValue(new Error('Query error'));

      await expect(service.read(tagId)).rejects.toThrow('Query error');

      expect(repository.findOne).toHaveBeenCalledWith({
        where: { dbId: tagId },
      });
    });
  });

  describe('remove', () => {
    it('should remove existing tag', async () => {
      const tagId = 1;
      const logSpy = jest.spyOn(Logger, 'log').mockImplementation();

      repository.findOne.mockResolvedValue(mockTagEntity);
      repository.remove.mockResolvedValue(mockTagEntity);

      const result = await service.remove(tagId);

      expect(repository.findOne).toHaveBeenCalledWith({
        where: { dbId: tagId },
      });
      expect(repository.remove).toHaveBeenCalledWith(mockTagEntity);
      expect(logSpy).toHaveBeenCalledWith('Removing tag from database', tagId);
      expect(result).toEqual(mockTagEntity);

      logSpy.mockRestore();
    });

    it('should return null when tag not found for removal', async () => {
      const tagId = 999;
      const logSpy = jest.spyOn(Logger, 'log').mockImplementation();

      repository.findOne.mockResolvedValue(null);

      const result = await service.remove(tagId);

      expect(repository.findOne).toHaveBeenCalledWith({
        where: { dbId: tagId },
      });
      expect(repository.remove).not.toHaveBeenCalled();
      expect(logSpy).toHaveBeenCalledWith('Removing tag from database', tagId);
      expect(result).toBeNull();

      logSpy.mockRestore();
    });

    it('should handle repository errors during find for removal', async () => {
      const tagId = 1;
      const logSpy = jest.spyOn(Logger, 'log').mockImplementation();

      repository.findOne.mockRejectedValue(new Error('Find error'));

      await expect(service.remove(tagId)).rejects.toThrow('Find error');

      expect(repository.findOne).toHaveBeenCalledWith({
        where: { dbId: tagId },
      });
      expect(repository.remove).not.toHaveBeenCalled();
      expect(logSpy).toHaveBeenCalledWith('Removing tag from database', tagId);

      logSpy.mockRestore();
    });

    it('should handle repository errors during removal', async () => {
      const tagId = 1;
      const logSpy = jest.spyOn(Logger, 'log').mockImplementation();

      repository.findOne.mockResolvedValue(mockTagEntity);
      repository.remove.mockRejectedValue(new Error('Remove error'));

      await expect(service.remove(tagId)).rejects.toThrow('Remove error');

      expect(repository.findOne).toHaveBeenCalledWith({
        where: { dbId: tagId },
      });
      expect(repository.remove).toHaveBeenCalledWith(mockTagEntity);
      expect(logSpy).toHaveBeenCalledWith('Removing tag from database', tagId);

      logSpy.mockRestore();
    });
  });
});
