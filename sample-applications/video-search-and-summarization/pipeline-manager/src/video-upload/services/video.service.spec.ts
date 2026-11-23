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
import { of, throwError } from 'rxjs';
import { AxiosError } from 'axios';
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
    url: 'test-video-id/test-video.mp4',
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
      setEmbeddingFlags: jest.fn(),
    };

    const datastoreServiceMock = {
      uploadFile: jest.fn(),
      copyObject: jest.fn(),
      deleteFile: jest.fn(),
      deleteObject: jest.fn(),
      getFile: jest.fn(),
      getObjectName: jest.fn(),
      bucket: 'test-bucket',
    };

    const videoValidatorServiceMock = {
      isStreamable: jest.fn(),
      resolveSafeUploadPath: jest.fn((value: string) => value),
    };

    const tagsServiceMock = {
      addTags: jest.fn(),
    };

    const dataPrepShimServiceMock = {
      createEmbeddings: jest.fn(),
      createEmbeddingsBatch: jest.fn(),
      getBatchJobStatus: jest.fn(),
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

    it('should merge and persist additional tags before creating embeddings', async () => {
      const videoId = 'test-video-id';
      const mergedTags = ['tag1', 'tag2', 'new-tag'];
      const updatedVideo = { ...mockVideo, tags: mergedTags };
      const mockEmbeddingsResponse = { success: true };

      videoDbService.read.mockResolvedValue(mockVideo);
      videoDbService.update.mockResolvedValue(updatedVideo as any);
      dataPrepShimService.createEmbeddings.mockReturnValue(of({
        data: mockEmbeddingsResponse,
        status: 200,
        statusText: 'OK',
        headers: {},
        config: {},
      } as any));

      const result = await service.createSearchEmbeddings(videoId, ['new-tag', 'tag1']);

      expect(videoDbService.update).toHaveBeenCalledWith(videoId, { tags: mergedTags });
      expect(tagsService.addTags).toHaveBeenCalledWith(['new-tag', 'tag1']);
      expect(dataPrepShimService.createEmbeddings).toHaveBeenCalledWith({
        bucket_name: updatedVideo.dataStore!.bucket,
        video_id: updatedVideo.dataStore!.objectName,
        video_name: updatedVideo.dataStore!.fileName,
        tags: mergedTags,
      } as DataPrepMinioDTO);
      expect(result.data).toEqual(mockEmbeddingsResponse);
    });

    it('should use the original display filename for embeddings payload when it differs from the stored object name', async () => {
      const videoId = 'test-video-id';
      const videoWithDifferentDisplayName = {
        ...mockVideo,
        url: 'test-video-id/original_-_Copy.mp4',
        dataStore: {
          ...mockVideo.dataStore!,
          fileName: 'original - Copy.mp4',
        },
      };
      const mockEmbeddingsResponse = { success: true };

      videoDbService.read.mockResolvedValue(videoWithDifferentDisplayName);
      dataPrepShimService.createEmbeddings.mockReturnValue(of({
        data: mockEmbeddingsResponse,
        status: 200,
        statusText: 'OK',
        headers: {},
        config: {},
      } as any));

      await service.createSearchEmbeddings(videoId);

      expect(dataPrepShimService.createEmbeddings).toHaveBeenCalledWith({
        bucket_name: videoWithDifferentDisplayName.dataStore!.bucket,
        video_id: videoWithDifferentDisplayName.dataStore!.objectName,
        video_name: 'original - Copy.mp4',
        tags: videoWithDifferentDisplayName.tags,
      } as DataPrepMinioDTO);
    });
  });

  describe('getSearchEmbeddingsJobStatus', () => {
    const jobStatus = (items: any[]) => ({
      data: {
        job_id: 'job-1',
        state: 'completed',
        total: items.length,
        completed: 0,
        failed: 0,
        items,
      },
      status: 200,
      statusText: 'OK',
      headers: {},
      config: {},
    }) as any;

    it('cleans up videos a batch item rejected as duplicate content', async () => {
      dataPrepShimService.getBatchJobStatus.mockReturnValue(
        of(
          jobStatus([
            {
              identifier: 'dup.mp4',
              video_id: 'test-video-id',
              status: 'error',
              message:
                "A video with identical content already exists (existing video_id: 'other-id').",
            },
          ]),
        ),
      );
      videoDbService.read.mockResolvedValue(mockVideo);
      videoDbService.remove.mockResolvedValue(mockVideo as any);

      const result = await service.getSearchEmbeddingsJobStatus('job-1');

      expect(datastoreService.deleteObject).toHaveBeenCalledWith(
        mockVideo.dataStore!.objectName,
      );
      expect(videoDbService.remove).toHaveBeenCalledWith('test-video-id');
      expect(result.job_id).toBe('job-1');
    });

    it('leaves successful and non-duplicate failed items untouched', async () => {
      dataPrepShimService.getBatchJobStatus.mockReturnValue(
        of(
          jobStatus([
            { identifier: 'ok.mp4', video_id: 'vid-ok', status: 'success' },
            {
              identifier: 'boom.mp4',
              video_id: 'vid-boom',
              status: 'error',
              message: 'Embedding backend unavailable',
            },
          ]),
        ),
      );

      await service.getSearchEmbeddingsJobStatus('job-1');

      expect(datastoreService.deleteObject).not.toHaveBeenCalled();
      expect(videoDbService.remove).not.toHaveBeenCalled();
    });

    it('still returns the job status when cleanup fails', async () => {
      dataPrepShimService.getBatchJobStatus.mockReturnValue(
        of(
          jobStatus([
            {
              identifier: 'dup.mp4',
              video_id: 'test-video-id',
              status: 'error',
              message: 'A video with identical content already exists',
            },
          ]),
        ),
      );
      videoDbService.read.mockRejectedValue(new Error('db down'));

      const result = await service.getSearchEmbeddingsJobStatus('job-1');

      expect(result.job_id).toBe('job-1');
    });
  });

  describe('embedding status', () => {
    const axiosResponse = (data: any) =>
      ({ data, status: 201, statusText: 'Created', headers: {}, config: {} }) as any;

    const jobStatus = (state: string, items: any[]) =>
      axiosResponse({
        job_id: 'job-1',
        state,
        total: items.length,
        completed: items.filter((i) => i.status === 'success').length,
        failed: items.filter((i) => i.status === 'error').length,
        items,
      });

    const httpError = (status?: number, code?: string) =>
      new AxiosError(
        'request failed',
        code,
        undefined,
        undefined,
        status
          ? ({ status, data: { message: 'boom' } } as any)
          : undefined,
      );

    afterEach(() => {
      service.onModuleDestroy();
      jest.useRealTimers();
    });

    describe('createSearchEmbeddings', () => {
      it('records searchEmbeddings=true and refreshes the cache on success', async () => {
        const indexed = { ...mockVideo, searchEmbeddings: true };
        videoDbService.read.mockResolvedValue(mockVideo);
        videoDbService.setEmbeddingFlags.mockResolvedValue(indexed as any);
        dataPrepShimService.createEmbeddings.mockReturnValue(
          of(axiosResponse({ status: 'success', message: 'ok' })),
        );

        await service.createSearchEmbeddings(mockVideo.videoId);

        expect(videoDbService.setEmbeddingFlags).toHaveBeenCalledWith(
          mockVideo.videoId,
          { searchEmbeddings: true },
        );
        expect(await service.getVideo(mockVideo.videoId)).toEqual(indexed);
      });

      it('records searchEmbeddings=false when data-prep reports a non-success status', async () => {
        videoDbService.read.mockResolvedValue(mockVideo);
        dataPrepShimService.createEmbeddings.mockReturnValue(
          of(axiosResponse({ status: 'error', message: 'nope' })),
        );

        await service.createSearchEmbeddings(mockVideo.videoId);

        expect(videoDbService.setEmbeddingFlags).toHaveBeenCalledWith(
          mockVideo.videoId,
          { searchEmbeddings: false },
        );
      });

      it('records searchEmbeddings=false and rethrows when data-prep answers with an error', async () => {
        const error = httpError(502);
        videoDbService.read.mockResolvedValue(mockVideo);
        dataPrepShimService.createEmbeddings.mockReturnValue(
          throwError(() => error),
        );

        await expect(
          service.createSearchEmbeddings(mockVideo.videoId),
        ).rejects.toBe(error);
        expect(videoDbService.setEmbeddingFlags).toHaveBeenCalledWith(
          mockVideo.videoId,
          { searchEmbeddings: false },
        );
      });

      it('leaves the status unknown when the request times out', async () => {
        const error = httpError(undefined, 'ECONNABORTED');
        videoDbService.read.mockResolvedValue(mockVideo);
        dataPrepShimService.createEmbeddings.mockReturnValue(
          throwError(() => error),
        );

        await expect(
          service.createSearchEmbeddings(mockVideo.videoId),
        ).rejects.toBe(error);
        expect(videoDbService.setEmbeddingFlags).not.toHaveBeenCalled();
      });

      it('never downgrades a video that is already indexed', async () => {
        videoDbService.read.mockResolvedValue({
          ...mockVideo,
          searchEmbeddings: true,
        });
        dataPrepShimService.createEmbeddings.mockReturnValue(
          throwError(() => httpError(500)),
        );

        await expect(
          service.createSearchEmbeddings(mockVideo.videoId),
        ).rejects.toBeDefined();
        expect(videoDbService.setEmbeddingFlags).not.toHaveBeenCalled();
      });

      it('still returns the data-prep response when recording the status fails', async () => {
        const warn = jest.spyOn(Logger, 'warn').mockImplementation();
        videoDbService.read.mockResolvedValue(mockVideo);
        videoDbService.setEmbeddingFlags.mockRejectedValue(new Error('db down'));
        dataPrepShimService.createEmbeddings.mockReturnValue(
          of(axiosResponse({ status: 'success', message: 'ok' })),
        );

        const result = await service.createSearchEmbeddings(mockVideo.videoId);

        expect(result.data.status).toBe('success');
        expect(warn).toHaveBeenCalled();
        warn.mockRestore();
      });
    });

    describe('onEmbeddingsStatus', () => {
      it('records the reported kind once and skips repeats', async () => {
        const indexed = { ...mockVideo, textEmbeddings: true };
        videoDbService.read.mockResolvedValue(mockVideo);
        videoDbService.setEmbeddingFlags.mockResolvedValue(indexed as any);

        const event = {
          videoId: mockVideo.videoId,
          kind: 'textEmbeddings' as const,
          created: true,
        };
        await service.onEmbeddingsStatus(event);
        await service.onEmbeddingsStatus(event);

        expect(videoDbService.setEmbeddingFlags).toHaveBeenCalledTimes(1);
        expect(videoDbService.setEmbeddingFlags).toHaveBeenCalledWith(
          mockVideo.videoId,
          { textEmbeddings: true },
        );
      });

      it('ignores videos that no longer exist', async () => {
        videoDbService.read.mockResolvedValue(null);

        await service.onEmbeddingsStatus({
          videoId: 'gone',
          kind: 'textEmbeddings',
          created: true,
        });

        expect(videoDbService.setEmbeddingFlags).not.toHaveBeenCalled();
      });
    });

    describe('batch jobs', () => {
      it('records each finished item when the job status is read', async () => {
        videoDbService.read.mockImplementation(async (videoId: string) => ({
          ...mockVideo,
          videoId,
        }));
        dataPrepShimService.getBatchJobStatus.mockReturnValue(
          of(
            jobStatus('completed_with_errors', [
              { identifier: 'a', video_id: 'vid-ok', status: 'success' },
              {
                identifier: 'b',
                video_id: 'vid-bad',
                status: 'error',
                message: 'Embedding backend unavailable',
              },
              { identifier: 'c', video_id: 'vid-wait', status: 'pending' },
            ]),
          ),
        );

        await service.getSearchEmbeddingsJobStatus('job-1');

        expect(videoDbService.setEmbeddingFlags).toHaveBeenCalledWith('vid-ok', {
          searchEmbeddings: true,
        });
        expect(videoDbService.setEmbeddingFlags).toHaveBeenCalledWith('vid-bad', {
          searchEmbeddings: false,
        });
        expect(videoDbService.setEmbeddingFlags).toHaveBeenCalledTimes(2);
      });

      it('does not record a status for items rejected as duplicate content', async () => {
        videoDbService.read.mockResolvedValue(null);
        dataPrepShimService.getBatchJobStatus.mockReturnValue(
          of(
            jobStatus('completed_with_errors', [
              {
                identifier: 'dup',
                video_id: 'vid-dup',
                status: 'error',
                message: 'A video with identical content already exists',
              },
            ]),
          ),
        );

        await service.getSearchEmbeddingsJobStatus('job-1');

        expect(videoDbService.setEmbeddingFlags).not.toHaveBeenCalled();
      });

      it('follows a submitted job server-side until it reaches a terminal state', async () => {
        jest.useFakeTimers();
        videoDbService.read.mockResolvedValue(mockVideo);
        dataPrepShimService.createEmbeddingsBatch.mockReturnValue(
          of(axiosResponse({ job_id: 'job-1', accepted: 1 })),
        );
        dataPrepShimService.getBatchJobStatus
          .mockReturnValueOnce(
            of(
              jobStatus('running', [
                { identifier: 'a', video_id: mockVideo.videoId, status: 'running' },
              ]),
            ),
          )
          .mockReturnValue(
            of(
              jobStatus('completed', [
                { identifier: 'a', video_id: mockVideo.videoId, status: 'success' },
              ]),
            ),
          );

        await service.createSearchEmbeddingsBatch([mockVideo.videoId]);
        expect(dataPrepShimService.getBatchJobStatus).not.toHaveBeenCalled();

        await jest.advanceTimersByTimeAsync(VideoService.BATCH_TRACK_INTERVAL_MS);
        expect(videoDbService.setEmbeddingFlags).not.toHaveBeenCalled();

        await jest.advanceTimersByTimeAsync(VideoService.BATCH_TRACK_INTERVAL_MS);
        expect(videoDbService.setEmbeddingFlags).toHaveBeenCalledWith(
          mockVideo.videoId,
          { searchEmbeddings: true },
        );

        await jest.advanceTimersByTimeAsync(VideoService.BATCH_TRACK_INTERVAL_MS * 5);
        expect(dataPrepShimService.getBatchJobStatus).toHaveBeenCalledTimes(2);
      });

      it('stops following a job data-prep no longer knows', async () => {
        jest.useFakeTimers();
        videoDbService.read.mockResolvedValue(mockVideo);
        dataPrepShimService.createEmbeddingsBatch.mockReturnValue(
          of(axiosResponse({ job_id: 'job-1', accepted: 1 })),
        );
        dataPrepShimService.getBatchJobStatus.mockReturnValue(
          throwError(() => httpError(404)),
        );

        await service.createSearchEmbeddingsBatch([mockVideo.videoId]);
        await jest.advanceTimersByTimeAsync(VideoService.BATCH_TRACK_INTERVAL_MS * 5);

        expect(dataPrepShimService.getBatchJobStatus).toHaveBeenCalledTimes(1);
      });

      it('keeps following a job through transient poll failures', async () => {
        jest.useFakeTimers();
        const warn = jest.spyOn(Logger, 'warn').mockImplementation();
        videoDbService.read.mockResolvedValue(mockVideo);
        dataPrepShimService.createEmbeddingsBatch.mockReturnValue(
          of(axiosResponse({ job_id: 'job-1', accepted: 1 })),
        );
        dataPrepShimService.getBatchJobStatus
          .mockReturnValueOnce(throwError(() => httpError(503)))
          .mockReturnValue(
            of(
              jobStatus('completed', [
                { identifier: 'a', video_id: mockVideo.videoId, status: 'success' },
              ]),
            ),
          );

        await service.createSearchEmbeddingsBatch([mockVideo.videoId]);
        await jest.advanceTimersByTimeAsync(VideoService.BATCH_TRACK_INTERVAL_MS * 2);

        expect(videoDbService.setEmbeddingFlags).toHaveBeenCalledWith(
          mockVideo.videoId,
          { searchEmbeddings: true },
        );
        warn.mockRestore();
      });

      it('stops following jobs when the module is destroyed', async () => {
        jest.useFakeTimers();
        videoDbService.read.mockResolvedValue(mockVideo);
        dataPrepShimService.createEmbeddingsBatch.mockReturnValue(
          of(axiosResponse({ job_id: 'job-1', accepted: 1 })),
        );

        await service.createSearchEmbeddingsBatch([mockVideo.videoId]);
        service.onModuleDestroy();
        await jest.advanceTimersByTimeAsync(VideoService.BATCH_TRACK_INTERVAL_MS * 5);

        expect(dataPrepShimService.getBatchJobStatus).not.toHaveBeenCalled();
      });
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

    it('should preserve display filename while using sanitized object path', async () => {
      const originalNameWithSpaces = 'store aisle clip.mp4';
      datastoreService.getObjectName.mockReturnValue({
        objectPath: '/bucket/test-video-id/store_aisle_clip.mp4',
        fileExtn: '.mp4',
      });

      await service.uploadVideo(videoFilePath, originalNameWithSpaces, {});

      expect(datastoreService.uploadFile).toHaveBeenCalledWith(
        '/bucket/test-video-id/store_aisle_clip.mp4',
        videoFilePath,
      );
      expect(videoDbService.create).toHaveBeenCalledWith(
        expect.objectContaining({
          url: '/bucket/test-video-id/store_aisle_clip.mp4',
          dataStore: {
            bucket: 'test-bucket',
            fileName: originalNameWithSpaces,
            objectName: 'test-video-id',
          },
        }),
      );
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

  describe('copyVideo', () => {
    beforeEach(() => {
      (uuidv4 as jest.Mock).mockReturnValue('copy-video-id');
      videoDbService.read.mockResolvedValue(mockVideo);
      datastoreService.getObjectName.mockReturnValue({
        objectPath: 'copy-video-id/source.mp4',
        fileExtn: 'mp4',
      });
      datastoreService.copyObject.mockResolvedValue({} as any);
      videoDbService.create.mockImplementation(async (video: Video) => video);
      tagsService.addTags.mockResolvedValue(undefined);
    });

    it('should copy the stored file to a new id and keep the same name', async () => {
      const result = await service.copyVideo('test-video-id');

      expect(result).toBe('copy-video-id');
      expect(datastoreService.getObjectName).toHaveBeenCalledWith(
        'copy-video-id',
        'test-video.mp4',
      );
      expect(datastoreService.copyObject).toHaveBeenCalledWith(
        'test-video-id/test-video.mp4',
        'copy-video-id/source.mp4',
      );
      expect(videoDbService.create).toHaveBeenCalledWith({
        name: 'test-video.mp4',
        tags: ['tag1', 'tag2'],
        dataStore: {
          bucket: 'test-bucket',
          fileName: 'test-video.mp4',
          objectName: 'copy-video-id',
        },
        videoId: 'copy-video-id',
        createdAt: expect.any(String),
        updatedAt: expect.any(String),
        url: 'copy-video-id/source.mp4',
      });
      expect(await service.getVideo('copy-video-id')).toEqual(
        expect.objectContaining({ videoId: 'copy-video-id' }),
      );
    });

    it('should not carry over embedding flags or summaries', async () => {
      videoDbService.read.mockResolvedValue({
        ...mockVideo,
        searchEmbeddings: true,
        textEmbeddings: true,
        summaryId: 's1',
      } as any);

      await service.copyVideo('test-video-id');

      const created = videoDbService.create.mock.calls[0][0];
      expect(created).not.toHaveProperty('searchEmbeddings');
      expect(created).not.toHaveProperty('textEmbeddings');
      expect(created).not.toHaveProperty('summaryId');
    });

    it('should merge new tags into the source tags', async () => {
      await service.copyVideo('test-video-id', ['tag2', ' tag3 ', '']);

      expect(videoDbService.create).toHaveBeenCalledWith(
        expect.objectContaining({ tags: ['tag1', 'tag2', 'tag3'] }),
      );
      expect(tagsService.addTags).toHaveBeenCalledWith([
        'tag1',
        'tag2',
        'tag3',
      ]);
    });

    it('should leave the source video untouched', async () => {
      await service.copyVideo('test-video-id', ['tag3']);

      expect(videoDbService.update).not.toHaveBeenCalled();
      expect(datastoreService.deleteObject).not.toHaveBeenCalled();
    });

    it('should throw NotFoundException for an unknown video', async () => {
      videoDbService.read.mockResolvedValue(null as any);

      await expect(service.copyVideo('missing')).rejects.toThrow(
        NotFoundException,
      );
      expect(datastoreService.copyObject).not.toHaveBeenCalled();
    });

    it('should reject a video without a stored file', async () => {
      videoDbService.read.mockResolvedValue({
        ...mockVideo,
        dataStore: undefined,
      });

      await expect(service.copyVideo('test-video-id')).rejects.toThrow(
        UnprocessableEntityException,
      );
      expect(datastoreService.copyObject).not.toHaveBeenCalled();
    });

    it('should not create a record when the object copy fails', async () => {
      const errorSpy = jest.spyOn(Logger, 'error').mockImplementation();
      datastoreService.copyObject.mockRejectedValue(new Error('copy failed'));

      await expect(service.copyVideo('test-video-id')).rejects.toThrow(
        UnprocessableEntityException,
      );
      expect(videoDbService.create).not.toHaveBeenCalled();

      errorSpy.mockRestore();
    });

    it('should remove the copied object when saving the record fails', async () => {
      const errorSpy = jest.spyOn(Logger, 'error').mockImplementation();
      videoDbService.create.mockRejectedValue(new Error('db down'));

      await expect(service.copyVideo('test-video-id')).rejects.toThrow(
        UnprocessableEntityException,
      );
      expect(datastoreService.deleteObject).toHaveBeenCalledWith(
        'copy-video-id/source.mp4',
      );

      errorSpy.mockRestore();
    });

    it('should still return the copy when tag registration fails', async () => {
      const warnSpy = jest.spyOn(Logger, 'warn').mockImplementation();
      tagsService.addTags.mockRejectedValue(new Error('tags down'));

      await expect(service.copyVideo('test-video-id')).resolves.toBe(
        'copy-video-id',
      );

      warnSpy.mockRestore();
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