// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Test, TestingModule } from '@nestjs/testing';
import { PipelineController } from './pipeline.controller';
import { ChunkingService } from './queues/chunking.service';
import { EvamService } from 'src/evam/services/evam.service';

describe('PipelineController', () => {
  let controller: PipelineController;
  let chunkingService: ChunkingService;
  let evamService: EvamService;

  // Create mock services
  const mockChunkingService = {
    waiting: [] as any[],
    processing: [] as any[]
  };

  const mockEvamService = {
    inProgress: false
  };

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      controllers: [PipelineController],
      providers: [
        {
          provide: ChunkingService,
          useValue: mockChunkingService,
        },
        {
          provide: EvamService,
          useValue: mockEvamService,
        },
      ],
    }).compile();

    controller = module.get<PipelineController>(PipelineController);
    chunkingService = module.get<ChunkingService>(ChunkingService);
    evamService = module.get<EvamService>(EvamService);
  });

  it('should be defined', () => {
    expect(controller).toBeDefined();
  });

  describe('getFramesPipeline', () => {
    it('should return waiting and processing arrays from chunking service', () => {
      // Arrange
      mockChunkingService.waiting = ['frame1', 'frame2'];
      mockChunkingService.processing = ['frame3'];
      const mockRequest = {} as Request;

      // Act
      const result = controller.getFramesPipeline(mockRequest);

      // Assert
      expect(result).toEqual({
        waiting: ['frame1', 'frame2'],
        processing: ['frame3'],
      });
      expect(result.waiting).toBe(mockChunkingService.waiting);
      expect(result.processing).toBe(mockChunkingService.processing);
    });

    it('should return empty arrays when no frames are being processed', () => {
      // Arrange
      mockChunkingService.waiting = [];
      mockChunkingService.processing = [];
      const mockRequest = {} as Request;

      // Act
      const result = controller.getFramesPipeline(mockRequest);

      // Assert
      expect(result).toEqual({
        waiting: [],
        processing: [],
      });
    });
  });

  describe('getEvamPipeline', () => {
    it('should return chunkingInProgress status from evam service when true', () => {
      // Arrange
      mockEvamService.inProgress = true;

      // Act
      const result = controller.getEvamPipeline();

      // Assert
      expect(result).toEqual({ chunkingInProgress: true });
    });

    it('should return chunkingInProgress status from evam service when false', () => {
      // Arrange
      mockEvamService.inProgress = false;

      // Act
      const result = controller.getEvamPipeline();

      // Assert
      expect(result).toEqual({ chunkingInProgress: false });
    });
  });
});
