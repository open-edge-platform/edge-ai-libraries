// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Test, TestingModule } from '@nestjs/testing';
import { VideoDbService } from './video-db.service';
import { getRepositoryToken } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { VideoEntity } from '../models/video.entity';

describe('VideoDbService', () => {
  let service: VideoDbService;
  let repository: jest.Mocked<Repository<VideoEntity>>;

  const mockVideo = {
    videoId: 'test-video-123',
    name: 'test-video.mp4',
    url: '/path/to/video.mp4',
    tags: ['tag1', 'tag2'],
    createdAt: '2023-01-01T00:00:00.000Z',
    updatedAt: '2023-01-01T00:00:00.000Z'
  };

  const mockVideoEntity = {
    dbId: 1,
    ...mockVideo
  };

  beforeEach(async () => {
    const repositoryMock = {
      create: jest.fn(),
      save: jest.fn(),
      find: jest.fn(),
      findOne: jest.fn(),
      update: jest.fn(),
      delete: jest.fn(),
    };

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        VideoDbService,
        {
          provide: getRepositoryToken(VideoEntity),
          useValue: repositoryMock,
        },
      ],
    }).compile();

    service = module.get<VideoDbService>(VideoDbService);
    repository = module.get(getRepositoryToken(VideoEntity)) as jest.Mocked<Repository<VideoEntity>>;
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  describe('create', () => {
    it('should create and save a new video entity', async () => {
      const logSpy = jest.spyOn(require('@nestjs/common').Logger, 'log').mockImplementation();
      repository.create.mockReturnValue(mockVideoEntity as any);
      repository.save.mockResolvedValue(mockVideoEntity as any);

      const result = await service.create(mockVideo as any);

      expect(logSpy).toHaveBeenCalledWith('Adding video to database', mockVideo);
      expect(repository.create).toHaveBeenCalledWith(mockVideo);
      expect(repository.save).toHaveBeenCalledWith(mockVideoEntity);
      expect(result).toEqual(mockVideoEntity);

      logSpy.mockRestore();
    });

    it('should handle database errors during creation', async () => {
      const logSpy = jest.spyOn(require('@nestjs/common').Logger, 'log').mockImplementation();
      const dbError = new Error('Database save failed');
      
      repository.create.mockReturnValue(mockVideoEntity as any);
      repository.save.mockRejectedValue(dbError);

      await expect(service.create(mockVideo as any)).rejects.toThrow(dbError);
      expect(repository.create).toHaveBeenCalledWith(mockVideo);
      expect(repository.save).toHaveBeenCalledWith(mockVideoEntity);

      logSpy.mockRestore();
    });
  });

  describe('readAll', () => {
    it('should return all videos from database', async () => {
      const mockVideos = [mockVideoEntity, { ...mockVideoEntity, dbId: 2, videoId: 'video-456' }];
      repository.find.mockResolvedValue(mockVideos as any);

      const result = await service.readAll();

      expect(repository.find).toHaveBeenCalledWith();
      expect(result).toEqual(mockVideos);
    });

    it('should return empty array when no videos exist', async () => {
      repository.find.mockResolvedValue([]);

      const result = await service.readAll();

      expect(repository.find).toHaveBeenCalledWith();
      expect(result).toEqual([]);
    });

    it('should handle database errors during readAll', async () => {
      const dbError = new Error('Database find failed');
      repository.find.mockRejectedValue(dbError);

      await expect(service.readAll()).rejects.toThrow(dbError);
      expect(repository.find).toHaveBeenCalledWith();
    });
  });

  describe('read', () => {
    it('should return a video by videoId', async () => {
      repository.findOne.mockResolvedValue(mockVideoEntity as any);

      const result = await service.read('test-video-123');

      expect(repository.findOne).toHaveBeenCalledWith({
        where: { videoId: 'test-video-123' },
      });
      expect(result).toEqual(mockVideoEntity);
    });

    it('should return null when video is not found', async () => {
      repository.findOne.mockResolvedValue(null);

      const result = await service.read('non-existent-video');

      expect(repository.findOne).toHaveBeenCalledWith({
        where: { videoId: 'non-existent-video' },
      });
      expect(result).toBeNull();
    });

    it('should return null when findOne returns undefined', async () => {
      repository.findOne.mockResolvedValue(undefined as any);

      const result = await service.read('test-video-123');

      expect(repository.findOne).toHaveBeenCalledWith({
        where: { videoId: 'test-video-123' },
      });
      expect(result).toBeNull();
    });

    it('should handle database errors during read', async () => {
      const dbError = new Error('Database findOne failed');
      repository.findOne.mockRejectedValue(dbError);

      await expect(service.read('test-video-123')).rejects.toThrow(dbError);
      expect(repository.findOne).toHaveBeenCalledWith({
        where: { videoId: 'test-video-123' },
      });
    });
  });

  describe('update', () => {
    it('should update an existing video', async () => {
      const updateData = {
        name: 'updated-video.mp4',
        tags: ['updated-tag']
      };
      const updatedVideoEntity = {
        ...mockVideoEntity,
        ...updateData,
        updatedAt: expect.any(String)
      };

      // Mock the read method call within update
      jest.spyOn(service, 'read').mockResolvedValue(mockVideoEntity as any);
      repository.save.mockResolvedValue(updatedVideoEntity as any);

      const result = await service.update('test-video-123', updateData);

      expect(service.read).toHaveBeenCalledWith('test-video-123');
      expect(repository.save).toHaveBeenCalledWith({
        ...mockVideoEntity,
        ...updateData,
        updatedAt: expect.any(String)
      });
      expect(result).toEqual(updatedVideoEntity);
    });

    it('should return null when video to update does not exist', async () => {
      const updateData = { name: 'updated-video.mp4' };
      
      // Mock the read method call within update
      jest.spyOn(service, 'read').mockResolvedValue(null);

      const result = await service.update('non-existent-video', updateData);

      expect(service.read).toHaveBeenCalledWith('non-existent-video');
      expect(repository.save).not.toHaveBeenCalled();
      expect(result).toBeNull();
    });

    it('should handle partial updates correctly', async () => {
      const updateData = { name: 'new-name.mp4' };
      const updatedVideoEntity = {
        ...mockVideoEntity,
        name: 'new-name.mp4',
        updatedAt: expect.any(String)
      };

      jest.spyOn(service, 'read').mockResolvedValue(mockVideoEntity as any);
      repository.save.mockResolvedValue(updatedVideoEntity as any);

      const result = await service.update('test-video-123', updateData);

      expect(service.read).toHaveBeenCalledWith('test-video-123');
      expect(repository.save).toHaveBeenCalledWith({
        ...mockVideoEntity,
        name: 'new-name.mp4',
        updatedAt: expect.any(String)
      });
      expect(result).toEqual(updatedVideoEntity);
    });

    it('should update the updatedAt timestamp', async () => {
      const updateData = { name: 'updated-video.mp4' };
      
      jest.spyOn(service, 'read').mockResolvedValue(mockVideoEntity as any);
      repository.save.mockImplementation((entity) => Promise.resolve(entity as any));

      const beforeUpdate = new Date().toISOString();
      await service.update('test-video-123', updateData);

      const savedEntity = repository.save.mock.calls[0][0];
      expect(savedEntity.updatedAt).toBeDefined();
      expect(savedEntity.updatedAt).toBeTruthy();
      expect(typeof savedEntity.updatedAt).toBe('string');
    });

    it('should handle database errors during update', async () => {
      const updateData = { name: 'updated-video.mp4' };
      const dbError = new Error('Database save failed');

      jest.spyOn(service, 'read').mockResolvedValue(mockVideoEntity as any);
      repository.save.mockRejectedValue(dbError);

      await expect(service.update('test-video-123', updateData)).rejects.toThrow(dbError);
      expect(service.read).toHaveBeenCalledWith('test-video-123');
      expect(repository.save).toHaveBeenCalled();
    });

    it('should handle read errors during update', async () => {
      const updateData = { name: 'updated-video.mp4' };
      const readError = new Error('Database read failed');

      jest.spyOn(service, 'read').mockRejectedValue(readError);

      await expect(service.update('test-video-123', updateData)).rejects.toThrow(readError);
      expect(service.read).toHaveBeenCalledWith('test-video-123');
      expect(repository.save).not.toHaveBeenCalled();
    });
  });
});
