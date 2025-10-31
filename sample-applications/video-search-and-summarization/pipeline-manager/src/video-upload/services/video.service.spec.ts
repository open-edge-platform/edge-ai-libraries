// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Mock minio before any imports to prevent import errors
jest.mock('minio', () => ({
  Client: jest.fn().mockImplementation(() => ({
    bucketExists: jest.fn().mockResolvedValue(true),
    makeBucket: jest.fn().mockResolvedValue(undefined),
    putObject: jest.fn().mockResolvedValue({ etag: 'test-etag' }),
    getObject: jest.fn().mockResolvedValue({}),
    removeObject: jest.fn().mockResolvedValue(undefined),
    listObjects: jest.fn().mockReturnValue([]),
  })),
}));

// Mock TypeORM before any imports to prevent import errors
jest.mock('@nestjs/typeorm', () => ({
  InjectRepository: jest.fn(() => jest.fn()),
  TypeOrmModule: {
    forRoot: jest.fn(),
    forFeature: jest.fn(),
  },
}));

// Mock typeorm
// Mock TypeORM completely to avoid path-scurry issues
jest.mock('typeorm', () => {
  const mockDecorator = (...args: any[]) => {
    return (target: any, propertyKey?: string | symbol, descriptor?: PropertyDescriptor) => {
      // Return the target unchanged for decorators in test environment
      return target;
    };
  };
  
  return {
    Entity: mockDecorator,
    Column: mockDecorator,
    PrimaryGeneratedColumn: mockDecorator,
    CreateDateColumn: mockDecorator,
    UpdateDateColumn: mockDecorator,
    Repository: jest.fn().mockImplementation(() => ({
      find: jest.fn(),
      findOne: jest.fn(),
      save: jest.fn(),
      create: jest.fn(),
      update: jest.fn(),
      delete: jest.fn()
    })),
    getRepository: jest.fn(),
    DataSource: jest.fn(),
    EntityRepository: mockDecorator
  };
});

// Mock path-scurry that's causing import issues in TypeORM
jest.mock('path-scurry', () => ({
  PathScurry: jest.fn(),
}));

import { Test, TestingModule } from '@nestjs/testing';
import { VideoService } from './video.service';
import { VideoDbService } from './video-db.service';
import { DatastoreService } from '../../datastore/services/datastore.service';
import { VideoValidatorService } from './video-validator.service';
import { TagsService } from './tags.service';
import { DataPrepShimService } from '../../data-prep/services/data-prep-shim.service';
import { Video, VideoDTO } from '../models/video.model';
import { NotFoundException, UnprocessableEntityException, Logger } from '@nestjs/common';
import { of } from 'rxjs';
import { DataPrepMinioDTO } from '../../data-prep/models/data-prep.models';
import * as fs from 'fs';
import { v4 as uuidv4 } from 'uuid';

// Mock the uuid module
jest.mock('uuid', () => ({
  v4: jest.fn(),
}));

// Mock the fs module
jest.mock('fs', () => ({
  unlink: jest.fn(),
}));

describe('VideoService', () => {
  let service: VideoService;
  let videoDbService: jest.Mocked<VideoDbService>;
  let datastoreService: jest.Mocked<DatastoreService>;
  let videoValidatorService: jest.Mocked<VideoValidatorService>;
  let tagsService: jest.Mocked<TagsService>;
  let dataPrepShimService: jest.Mocked<DataPrepShimService>;

  const mockVideo: Video = {
    videoId: 'test-video-id',
    name: 'test-video.mp4',
    url: '/test/path/to/video',
    tags: ['tag1', 'tag2'],
    createdAt: '2025-01-01T00:00:00.000Z',
    updatedAt: '2025-01-01T00:00:00.000Z',
    dataStore: {
      bucket: 'test-bucket',
      objectName: 'test-video-id',
      fileName: 'test-video.mp4',
    },
  };

  beforeEach(async () => {
    const videoDbServiceMock = {
      create: jest.fn(),
      readAll: jest.fn(),
      read: jest.fn(),
      update: jest.fn(),
      remove: jest.fn(),
    };

    const datastoreServiceMock = {
      uploadFile: jest.fn(),
      deleteFile: jest.fn(),
      getFile: jest.fn(),
      getObjectName: jest.fn(),
      bucket: 'test-bucket',
    };

    const videoValidatorServiceMock = {
      isStreamable: jest.fn(),
    };

    const tagsServiceMock = {
      addTags: jest.fn(),
    };

    const dataPrepShimServiceMock = {
      createEmbeddings: jest.fn(),
    };

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        VideoService,
        { provide: VideoDbService, useValue: videoDbServiceMock },
        { provide: DatastoreService, useValue: datastoreServiceMock },
        { provide: VideoValidatorService, useValue: videoValidatorServiceMock },
        { provide: TagsService, useValue: tagsServiceMock },
        { provide: DataPrepShimService, useValue: dataPrepShimServiceMock },
      ],
    }).compile();

    service = module.get<VideoService>(VideoService);
    videoDbService = module.get(VideoDbService) as jest.Mocked<VideoDbService>;
    datastoreService = module.get(DatastoreService) as jest.Mocked<DatastoreService>;
    videoValidatorService = module.get(VideoValidatorService) as jest.Mocked<VideoValidatorService>;
    tagsService = module.get(TagsService) as jest.Mocked<TagsService>;
    dataPrepShimService = module.get(DataPrepShimService) as jest.Mocked<DataPrepShimService>;

    // Reset mocks
    jest.clearAllMocks();
    (uuidv4 as jest.Mock).mockReturnValue('test-video-id');
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  describe('isStreamable', () => {
    it('should delegate to validator service', async () => {
      const videoPath = '/path/to/video.mp4';
      videoValidatorService.isStreamable.mockResolvedValue(true);

      const result = await service.isStreamable(videoPath);

      expect(videoValidatorService.isStreamable).toHaveBeenCalledWith(videoPath);
      expect(result).toBe(true);
    });

    it('should return false when validator returns false', async () => {
      const videoPath = '/path/to/video.avi';
      videoValidatorService.isStreamable.mockResolvedValue(false);

      const result = await service.isStreamable(videoPath);

      expect(videoValidatorService.isStreamable).toHaveBeenCalledWith(videoPath);
      expect(result).toBe(false);
    });
  });

  describe('createSearchEmbeddings', () => {
    it('should create embeddings for existing video', async () => {
      const videoId = 'test-video-id';
      const mockEmbeddingsResponse = { success: true };

      videoDbService.read.mockResolvedValue(mockVideo);
      dataPrepShimService.createEmbeddings.mockReturnValue(of({
        data: mockEmbeddingsResponse,
        status: 200,
        statusText: 'OK',
        headers: {},
        config: {},
      } as any));

      const result = await service.createSearchEmbeddings(videoId);

      expect(videoDbService.read).toHaveBeenCalledWith(videoId);
      expect(dataPrepShimService.createEmbeddings).toHaveBeenCalledWith({
        bucket_name: mockVideo.dataStore!.bucket,
        video_id: mockVideo.dataStore!.objectName,
        video_name: mockVideo.dataStore!.fileName,
        tags: mockVideo.tags,
      } as DataPrepMinioDTO);
      expect(result.data).toEqual(mockEmbeddingsResponse);
    });

    it('should throw NotFoundException when video not found', async () => {
      const videoId = 'non-existent-id';
      videoDbService.read.mockResolvedValue(null);

      await expect(service.createSearchEmbeddings(videoId)).rejects.toThrow(NotFoundException);
      expect(videoDbService.read).toHaveBeenCalledWith(videoId);
    });

    it('should throw UnprocessableEntityException when video has no dataStore', async () => {
      const videoId = 'test-video-id';
      const videoWithoutDataStore = { ...mockVideo, dataStore: undefined };
      videoDbService.read.mockResolvedValue(videoWithoutDataStore);

      await expect(service.createSearchEmbeddings(videoId)).rejects.toThrow(
        UnprocessableEntityException,
      );
      expect(videoDbService.read).toHaveBeenCalledWith(videoId);
    });

    it('should handle video with no tags', async () => {
      const videoId = 'test-video-id';
      const videoWithoutTags = { ...mockVideo, tags: [] };
      const mockEmbeddingsResponse = { success: true };

      videoDbService.read.mockResolvedValue(videoWithoutTags);
      dataPrepShimService.createEmbeddings.mockReturnValue(of({
        data: mockEmbeddingsResponse,
        status: 200,
        statusText: 'OK',
        headers: {},
        config: {},
      } as any));

      const result = await service.createSearchEmbeddings(videoId);

      expect(dataPrepShimService.createEmbeddings).toHaveBeenCalledWith({
        bucket_name: mockVideo.dataStore!.bucket,
        video_id: mockVideo.dataStore!.objectName,
        video_name: mockVideo.dataStore!.fileName,
        tags: [],
      } as DataPrepMinioDTO);
      expect(result.data).toEqual(mockEmbeddingsResponse);
    });
  });

  describe('uploadVideo', () => {
    const videoFilePath = '/tmp/test-video.mp4';
    const videoFileName = 'test-video.mp4';
    const videoData: VideoDTO = {
      name: 'Custom Video Name',
      tagsArray: ['tag1', 'tag2'],
    };

    beforeEach(() => {
      datastoreService.getObjectName.mockReturnValue({
        objectPath: '/bucket/test-video-id/test-video.mp4',
        fileExtn: '.mp4',
      });
      datastoreService.uploadFile.mockResolvedValue({} as any);
      videoDbService.create.mockResolvedValue(mockVideo);
      tagsService.addTags.mockResolvedValue(undefined);
      (fs.unlink as unknown as jest.Mock).mockImplementation((path, callback) => callback(null));
    });

    it('should successfully upload video with tags', async () => {
      const logSpy = jest.spyOn(Logger, 'log').mockImplementation();

      const result = await service.uploadVideo(videoFilePath, videoFileName, videoData);

      expect(datastoreService.getObjectName).toHaveBeenCalledWith('test-video-id', videoFileName);
      expect(datastoreService.uploadFile).toHaveBeenCalledWith(
        '/bucket/test-video-id/test-video.mp4',
        videoFilePath,
      );
      expect(videoDbService.create).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'Custom Video Name',
          tags: ['tag1', 'tag2'],
          videoId: 'test-video-id',
          dataStore: {
            bucket: 'test-bucket',
            fileName: videoFileName,
            objectName: 'test-video-id',
          },
        }),
      );
      expect(tagsService.addTags).toHaveBeenCalledWith(['tag1', 'tag2']);
      expect(fs.unlink).toHaveBeenCalledWith(videoFilePath, expect.any(Function));
      expect(result).toBe('test-video-id');

      logSpy.mockRestore();
    });

    it('should upload video without tags', async () => {
      const videoDataWithoutTags: VideoDTO = { name: 'Video Without Tags' };

      const result = await service.uploadVideo(videoFilePath, videoFileName, videoDataWithoutTags);

      expect(videoDbService.create).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'Video Without Tags',
          tags: [],
        }),
      );
      expect(tagsService.addTags).not.toHaveBeenCalled();
      expect(result).toBe('test-video-id');
    });

    it('should use filename as name when no custom name provided', async () => {
      const videoDataWithoutName: VideoDTO = { tagsArray: ['tag1'] };

      const result = await service.uploadVideo(videoFilePath, videoFileName, videoDataWithoutName);

      expect(videoDbService.create).toHaveBeenCalledWith(
        expect.objectContaining({
          name: videoFileName,
        }),
      );
      expect(result).toBe('test-video-id');
    });

    it('should handle datastore upload error', async () => {
      const errorSpy = jest.spyOn(Logger, 'error').mockImplementation();
      datastoreService.uploadFile.mockRejectedValue(new Error('Upload failed'));

      await expect(service.uploadVideo(videoFilePath, videoFileName, videoData)).rejects.toThrow(
        UnprocessableEntityException,
      );

      expect(datastoreService.uploadFile).toHaveBeenCalled();
      expect(errorSpy).toHaveBeenCalledWith('Error uploading video file to object storage', expect.any(Error));

      errorSpy.mockRestore();
    });

    it('should handle database save error', async () => {
      const errorSpy = jest.spyOn(Logger, 'error').mockImplementation();
      videoDbService.create.mockRejectedValue(new Error('Database error'));

      await expect(service.uploadVideo(videoFilePath, videoFileName, videoData)).rejects.toThrow(
        UnprocessableEntityException,
      );

      expect(videoDbService.create).toHaveBeenCalled();
      expect(errorSpy).toHaveBeenCalledWith('Error saving video to database', expect.any(Error));

      errorSpy.mockRestore();
    });

    it('should handle file deletion error gracefully', async () => {
      const errorSpy = jest.spyOn(Logger, 'error').mockImplementation();
      (fs.unlink as unknown as jest.Mock).mockImplementation((path, callback) => 
        callback(new Error('File deletion failed'))
      );

      const result = await service.uploadVideo(videoFilePath, videoFileName, videoData);

      expect(result).toBe('test-video-id');
      expect(errorSpy).toHaveBeenCalledWith('Error deleting file', expect.any(Error));

      errorSpy.mockRestore();
    });

    it('should add tags to service when video has tags', async () => {
      const logSpy = jest.spyOn(Logger, 'log').mockImplementation();

      await service.uploadVideo(videoFilePath, videoFileName, videoData);

      expect(logSpy).toHaveBeenCalledWith('Adding video tags', ['tag1', 'tag2']);
      expect(tagsService.addTags).toHaveBeenCalledWith(['tag1', 'tag2']);

      logSpy.mockRestore();
    });
  });

  describe('getVideos', () => {
    it('should return all videos and populate cache', async () => {
      const mockVideos = [mockVideo, { ...mockVideo, videoId: 'video-2', name: 'video2.mp4' }];
      videoDbService.readAll.mockResolvedValue(mockVideos);

      const result = await service.getVideos();

      expect(videoDbService.readAll).toHaveBeenCalled();
      expect(result).toEqual(mockVideos);
      
      // Verify cache is populated
      const cachedVideo = await service.getVideo(mockVideo.videoId);
      expect(cachedVideo).toEqual(mockVideo);
    });

    it('should return empty array when no videos exist', async () => {
      videoDbService.readAll.mockResolvedValue([]);

      const result = await service.getVideos();

      expect(result).toEqual([]);
    });

    it('should handle null response from database', async () => {
      videoDbService.readAll.mockResolvedValue(null as any);

      await expect(service.getVideos()).rejects.toThrow();
    });
  });

  describe('getVideo', () => {
    it('should return video from cache when available', async () => {
      // First populate cache
      videoDbService.readAll.mockResolvedValue([mockVideo]);
      await service.getVideos();

      // Clear database mock calls
      videoDbService.read.mockClear();

      const result = await service.getVideo(mockVideo.videoId);

      expect(result).toEqual(mockVideo);
      expect(videoDbService.read).not.toHaveBeenCalled();
    });

    it('should fetch video from database when not in cache', async () => {
      videoDbService.read.mockResolvedValue(mockVideo);

      const result = await service.getVideo(mockVideo.videoId);

      expect(videoDbService.read).toHaveBeenCalledWith(mockVideo.videoId);
      expect(result).toEqual(mockVideo);
    });

    it('should return null when video not found in database', async () => {
      videoDbService.read.mockResolvedValue(null);

      const result = await service.getVideo('non-existent-id');

      expect(videoDbService.read).toHaveBeenCalledWith('non-existent-id');
      expect(result).toBeNull();
    });

    it('should cache video after fetching from database', async () => {
      videoDbService.read.mockResolvedValue(mockVideo);

      // First call fetches from database
      const result1 = await service.getVideo(mockVideo.videoId);
      expect(result1).toEqual(mockVideo);
      expect(videoDbService.read).toHaveBeenCalledTimes(1);

      // Second call should use cache
      videoDbService.read.mockClear();
      const result2 = await service.getVideo(mockVideo.videoId);
      expect(result2).toEqual(mockVideo);
      expect(videoDbService.read).not.toHaveBeenCalled();
    });

    it('should handle undefined response from database', async () => {
      videoDbService.read.mockResolvedValue(undefined as any);

      const result = await service.getVideo('test-id');

      expect(result).toBeNull();
    });
  });
});