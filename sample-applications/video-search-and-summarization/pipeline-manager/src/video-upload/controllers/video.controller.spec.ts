// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Test, TestingModule } from '@nestjs/testing';
import { NotFoundException, UnprocessableEntityException } from '@nestjs/common';
import { VideoController } from './video.controller';
import { VideoService } from '../services/video.service';
import { FeaturesService } from '../../features/features.service';
import { VideoValidatorService } from '../services/video-validator.service';
import { FEATURE_STATE } from '../../features/features.model';
import { VideoDTO } from '../models/video.model';

describe('VideoController', () => {
  let controller: VideoController;
  let videoService: jest.Mocked<VideoService>;
  let featuresService: jest.Mocked<FeaturesService>;
  let videoValidatorService: jest.Mocked<VideoValidatorService>;

  const mockVideo = {
    id: 'test-video-123',
    name: 'test-video.mp4',
    path: '/path/to/video.mp4',
    tags: ['tag1', 'tag2'],
    createdAt: '2025-01-01T00:00:00.000Z'
  };

  const mockVideos = [mockVideo, { id: 'video2', name: 'video2.mp4', path: '/path/to/video2.mp4' }];

  const mockFile: Express.Multer.File = {
    fieldname: 'video',
    originalname: 'test-video.mp4',
    encoding: '7bit',
    mimetype: 'video/mp4',
    destination: '/tmp',
    filename: 'test-video-123.mp4',
    path: '/tmp/test-video-123.mp4',
    size: 1000000,
    stream: null as any,
    buffer: null as any
  };

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      controllers: [VideoController],
      providers: [
        {
          provide: VideoService,
          useValue: {
            getVideos: jest.fn().mockResolvedValue(mockVideos),
            getVideo: jest.fn().mockResolvedValue(mockVideo),
            uploadVideo: jest.fn().mockResolvedValue('test-video-123'),
            createSearchEmbeddings: jest.fn().mockResolvedValue({
              data: { status: 'success', embeddings: [] }
            })
          }
        },
        {
          provide: FeaturesService,
          useValue: {
            getFeatures: jest.fn().mockReturnValue({ search: FEATURE_STATE.ON }),
            hasFeature: jest.fn().mockReturnValue(true)
          }
        },
        {
          provide: VideoValidatorService,
          useValue: {
            isStreamable: jest.fn().mockResolvedValue(true)
          }
        }
      ]
    }).compile();

    controller = module.get<VideoController>(VideoController);
    videoService = module.get(VideoService);
    featuresService = module.get(FeaturesService);
    videoValidatorService = module.get(VideoValidatorService);
  });

  it('should be defined', () => {
    expect(controller).toBeDefined();
  });

  describe('videoUpload', () => {
    const reqBody: VideoDTO = {
      name: 'test-video.mp4',
      tags: 'tag1, tag2, tag3'
    };

    it('should upload video successfully with tags', async () => {
      const result = await controller.videoUpload(mockFile, reqBody);

      expect(result).toEqual({ videoId: 'test-video-123' });
      expect(videoValidatorService.isStreamable).toHaveBeenCalledWith(mockFile.path);
      expect(videoService.uploadVideo).toHaveBeenCalledWith(
        mockFile.path,
        mockFile.originalname,
        {
          name: mockFile.filename,
          tagsArray: ['tag1', 'tag2', 'tag3']
        }
      );
    });

    it('should upload video without tags', async () => {
      const reqBodyWithoutTags: VideoDTO = {
        name: 'test-video.mp4'
      };

      const result = await controller.videoUpload(mockFile, reqBodyWithoutTags);

      expect(result).toEqual({ videoId: 'test-video-123' });
      expect(videoService.uploadVideo).toHaveBeenCalledWith(
        mockFile.path,
        mockFile.originalname,
        {
          name: mockFile.filename,
          tagsArray: []
        }
      );
    });

    it('should throw error when file is not provided', async () => {
      await expect(controller.videoUpload(null as any, reqBody))
        .rejects.toThrow('File is required');
    });

    it('should throw UnprocessableEntityException when video is not streamable', async () => {
      videoValidatorService.isStreamable.mockResolvedValueOnce(false);

      await expect(controller.videoUpload(mockFile, reqBody))
        .rejects.toThrow(UnprocessableEntityException);
    });

    it('should handle tags parsing with empty string', async () => {
      const mockFile: Express.Multer.File = {
        buffer: Buffer.from('test video content'),
        originalname: 'test-video.mp4',
        mimetype: 'video/mp4',
        size: 1024,
        path: '/tmp/test-video-123.mp4',
        fieldname: 'file',
        encoding: '7bit',
        destination: '/tmp',
        filename: 'test-video-123.mp4',
        stream: null as any
      };
      const reqBody = { tags: '' };
      videoService.uploadVideo.mockResolvedValueOnce('test-video-123');

      const result = await controller.videoUpload(mockFile, reqBody);

      expect(result).toEqual({ videoId: 'test-video-123' });
      expect(videoService.uploadVideo).toHaveBeenCalledWith(
        mockFile.path,
        mockFile.originalname,
        {
          name: 'test-video-123.mp4',
          tagsArray: []
        }
      );
    });

    it('should handle upload service errors', async () => {
      videoService.uploadVideo.mockRejectedValueOnce(new Error('Upload failed'));

      await expect(controller.videoUpload(mockFile, reqBody))
        .rejects.toThrow('Upload failed');
    });
  });

  describe('getVideo', () => {
    it('should return video by ID', async () => {
      const videoId = 'test-video-123';
      const result = await controller.getVideo({ videoId });

      expect(result).toEqual({ video: mockVideo });
      expect(videoService.getVideo).toHaveBeenCalledWith(videoId);
    });

    it('should throw NotFoundException when video not found', async () => {
      videoService.getVideo.mockResolvedValueOnce(null);
      const videoId = 'non-existent-video';

      await expect(controller.getVideo({ videoId }))
        .rejects.toThrow(NotFoundException);
    });
  });

  describe('getVideos', () => {
    it('should return all videos', async () => {
      const result = await controller.getVideos();

      expect(result).toEqual({ videos: mockVideos });
      expect(videoService.getVideos).toHaveBeenCalled();
    });

    it('should handle empty videos array', async () => {
      videoService.getVideos.mockResolvedValueOnce([]);

      const result = await controller.getVideos();

      expect(result).toEqual({ videos: [] });
    });

    it('should handle service errors', async () => {
      videoService.getVideos.mockRejectedValueOnce(new Error('Service error'));

      await expect(controller.getVideos())
        .rejects.toThrow('Service error');
    });
  });

  describe('createSearchEmbeddings', () => {
    it('should successfully create search embeddings', async () => {
      const mockResponseData = { status: 'success', message: 'Embeddings created' };
      const mockResponse = {
        data: mockResponseData,
        status: 200,
        statusText: 'OK',
        headers: {},
        config: { headers: {} }
      } as any;
      videoService.createSearchEmbeddings.mockResolvedValueOnce(mockResponse);
      const videoId = 'test-video-123';

      const result = await controller.createSearchEmbeddings({ videoId });

      expect(videoService.createSearchEmbeddings).toHaveBeenCalledWith(videoId);
      expect(result).toBe(mockResponseData);
    });

    it('should throw UnprocessableEntityException when embedding creation fails', async () => {
      const mockFailedResponse = {
        data: { status: 'failed', message: 'Processing failed' },
        status: 422,
        statusText: 'Unprocessable Entity',
        headers: {},
        config: { headers: {} }
      } as any;
      videoService.createSearchEmbeddings.mockResolvedValueOnce(mockFailedResponse);
      const videoId = 'test-video-123';

      await expect(controller.createSearchEmbeddings({ videoId }))
        .rejects.toThrow(UnprocessableEntityException);
    });

    it('should handle service errors during embedding creation', async () => {
      videoService.createSearchEmbeddings.mockRejectedValueOnce(new Error('Embedding service error'));
      const videoId = 'test-video-123';

      await expect(controller.createSearchEmbeddings({ videoId }))
        .rejects.toThrow('Embedding service error');
    });

    it('should handle null data response', async () => {
      const mockNullResponse = {
        data: null,
        status: 200,
        statusText: 'OK',
        headers: {},
        config: { headers: {} }
      } as any;
      videoService.createSearchEmbeddings.mockResolvedValueOnce(mockNullResponse);
      const videoId = 'test-video-123';

      await expect(controller.createSearchEmbeddings({ videoId }))
        .rejects.toThrow(UnprocessableEntityException);
    });
  });

  describe('edge cases and validation', () => {
    it('should handle file validation errors', async () => {
      videoValidatorService.isStreamable.mockRejectedValueOnce(new Error('Validation error'));

      await expect(controller.videoUpload(mockFile, { name: 'test' }))
        .rejects.toThrow('Validation error');
    });

    it('should handle malformed tag strings', async () => {
      const reqBodyMalformedTags: VideoDTO = {
        name: 'test-video.mp4',
        tags: 'tag1,, , tag2,   tag3   '
      };

      const result = await controller.videoUpload(mockFile, reqBodyMalformedTags);

      expect(videoService.uploadVideo).toHaveBeenCalledWith(
        mockFile.path,
        mockFile.originalname,
        {
          name: mockFile.filename,
          tagsArray: ['tag1', '', '', 'tag2', 'tag3']
        }
      );
    });

    it('should handle different feature states', async () => {
      featuresService.getFeatures.mockReturnValueOnce({ search: FEATURE_STATE.ON, summary: FEATURE_STATE.ON });

      const videoId = 'test-video-123';
      const result = await controller.createSearchEmbeddings({ videoId });

      expect(result).toEqual({ status: 'success', embeddings: [] });
    });
  });
});
