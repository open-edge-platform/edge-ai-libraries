// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Test, TestingModule } from '@nestjs/testing';
import { BadRequestException, NotFoundException, InternalServerErrorException } from '@nestjs/common';
import { SummaryController } from './summary.controller';
import { VideoService } from 'src/video-upload/services/video.service';
import { AppConfigService } from 'src/video-upload/services/app-config.service';
import { StateService } from 'src/state-manager/services/state.service';
import { UiService } from 'src/state-manager/services/ui.service';
import { SummaryService } from '../services/summary.service';
import { SummaryPipelineDTO } from '../models/summary-pipeline.model';
import { EVAMPipelines } from 'src/evam/models/evam.model';

describe('SummaryController', () => {
  let controller: SummaryController;
  let videoService: jest.Mocked<VideoService>;
  let appConfigService: jest.Mocked<AppConfigService>;
  let stateService: jest.Mocked<StateService>;
  let uiService: jest.Mocked<UiService>;
  let summaryService: jest.Mocked<SummaryService>;

  const mockVideo = {
    id: 'test-video-id',
    name: 'test-video.mp4',
    path: '/path/to/video'
  };

  const mockState = {
    stateId: 'test-state-123',
    videoId: 'test-video-id',
    title: 'Test Summary'
  };

  const mockSystemConfig = {
    frameOverlap: 1,
    multiFrame: 3,
    evamPipeline: 'test-pipeline',
    framePrompt: 'test-prompt',
    summaryMapPrompt: 'test-map',
    summaryReducePrompt: 'test-reduce',
    summarySinglePrompt: 'test-single',
    audioModel: 'test-audio'
  };

  const mockUiState = {
    id: 'test-ui-state',
    stateId: 'test-state-123',
    progress: 50
  };

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      controllers: [SummaryController],
      providers: [
        {
          provide: VideoService,
          useValue: {
            getVideo: jest.fn().mockResolvedValue(mockVideo)
          }
        },
        {
          provide: AppConfigService,
          useValue: {
            systemConfig: jest.fn().mockReturnValue(mockSystemConfig)
          }
        },
        {
          provide: StateService,
          useValue: {
            fetchAll: jest.fn().mockReturnValue([mockState]),
            fetch: jest.fn().mockReturnValue(mockState),
            create: jest.fn().mockResolvedValue(mockState),
            exists: jest.fn().mockReturnValue(true)
          }
        },
        {
          provide: UiService,
          useValue: {
            getUiState: jest.fn().mockReturnValue(mockUiState)
          }
        },
        {
          provide: SummaryService,
          useValue: {
            removeSummary: jest.fn().mockResolvedValue(true)
          }
        }
      ]
    }).compile();

    controller = module.get<SummaryController>(SummaryController);
    videoService = module.get(VideoService);
    appConfigService = module.get(AppConfigService);
    stateService = module.get(StateService);
    uiService = module.get(UiService);
    summaryService = module.get(SummaryService);
  });

  it('should be defined', () => {
    expect(controller).toBeDefined();
  });

  describe('getSummary', () => {
    it('should return all summary states', () => {
      const result = controller.getSummary();

      expect(result).toEqual([mockState]);
      expect(stateService.fetchAll).toHaveBeenCalled();
    });
  });

  describe('getSummaryList', () => {
    it('should return UI states for all summaries', () => {
      const result = controller.getSummaryList();

      expect(result).toEqual([mockUiState]);
      expect(stateService.fetchAll).toHaveBeenCalled();
      expect(uiService.getUiState).toHaveBeenCalledWith(mockState.stateId);
    });
  });

  describe('getSummaryById', () => {
    it('should return UI state for specific summary', () => {
      const stateId = 'test-state-123';
      const result = controller.getSummaryById({ stateId });

      expect(result).toEqual(mockUiState);
      expect(uiService.getUiState).toHaveBeenCalledWith(stateId);
    });
  });

  describe('getSummaryRawById', () => {
    it('should return raw state for specific summary', () => {
      const stateId = 'test-state-123';
      const result = controller.getSummaryRawById({ stateId });

      expect(result).toEqual(mockState);
      expect(stateService.fetch).toHaveBeenCalledWith(stateId);
    });
  });

  describe('startSummaryPipeline', () => {
    const basicReqBody: SummaryPipelineDTO = {
      title: 'Test Summary Pipeline',
      videoId: 'test-video-id',
      sampling: {
        chunkDuration: 10,
        samplingFrame: 2,
        frameOverlap: 1,
        multiFrame: 3
      },
      evam: {
        evamPipeline: EVAMPipelines.OBJECT_DETECTION
      }
    };

    it('should start summary pipeline successfully', async () => {
      const result = await controller.startSummaryPipeline(basicReqBody);

      expect(result).toEqual({ summaryPipelineId: 'test-state-123' });
      expect(videoService.getVideo).toHaveBeenCalledWith('test-video-id');
      expect(stateService.create).toHaveBeenCalled();
    });

    it('should throw BadRequestException when title is missing', async () => {
      const reqBody = { ...basicReqBody, title: '' };

      await expect(controller.startSummaryPipeline(reqBody))
        .rejects.toThrow(BadRequestException);
    });

    it('should throw NotFoundException when video is not found', async () => {
      videoService.getVideo.mockResolvedValueOnce(null);

      await expect(controller.startSummaryPipeline(basicReqBody))
        .rejects.toThrow(NotFoundException);
    });

    it('should throw BadRequestException when evam pipeline is missing', async () => {
      const reqBody = { ...basicReqBody, evam: null as any };

      await expect(controller.startSummaryPipeline(reqBody))
        .rejects.toThrow(BadRequestException);
    });

    it('should handle multiFrame validation correctly', async () => {
      const reqBody = {
        ...basicReqBody,
        sampling: {
          chunkDuration: 10,
          samplingFrame: 2,
          frameOverlap: 1,
          multiFrame: 10 // Too high
        }
      };

      await expect(controller.startSummaryPipeline(reqBody))
        .rejects.toThrow(BadRequestException);
    });

    it('should handle multiFrame mismatch', async () => {
      const reqBody = {
        ...basicReqBody,
        sampling: {
          chunkDuration: 10,
          samplingFrame: 2,
          frameOverlap: 1,
          multiFrame: 5 // Should be 3 (1 + 2)
        }
      };

      await expect(controller.startSummaryPipeline(reqBody))
        .rejects.toThrow(BadRequestException);
    });

    it('should handle custom prompts', async () => {
      const reqBody = {
        ...basicReqBody,
        prompts: {
          framePrompt: 'Custom frame prompt',
          summaryMapPrompt: 'Custom map prompt',
          summaryReducePrompt: 'Custom reduce prompt',
          summarySinglePrompt: 'Custom single prompt'
        }
      };

      const result = await controller.startSummaryPipeline(reqBody);

      expect(result).toEqual({ summaryPipelineId: 'test-state-123' });
    });

    it('should handle custom audio configuration', async () => {
      const reqBody = {
        ...basicReqBody,
        audio: {
          audioModel: 'custom-audio-model'
        }
      };

      const result = await controller.startSummaryPipeline(reqBody);

      expect(result).toEqual({ summaryPipelineId: 'test-state-123' });
    });

    it('should throw TypeError when state creation returns null', async () => {
      stateService.create.mockResolvedValueOnce(null as any);

      await expect(controller.startSummaryPipeline(basicReqBody))
        .rejects.toThrow(TypeError);
    });

    it('should throw InternalServerErrorException when no video provided', async () => {
      const reqBody = { ...basicReqBody, videoId: '' };
      // videoService.getVideo won't be called since videoId is falsy

      await expect(controller.startSummaryPipeline(reqBody))
        .rejects.toThrow(InternalServerErrorException);
    });

    it('should throw NotFoundException when video not found', async () => {
      const reqBody = { ...basicReqBody, videoId: 'non-existent-video' };
      videoService.getVideo.mockResolvedValueOnce(null);

      await expect(controller.startSummaryPipeline(reqBody))
        .rejects.toThrow(NotFoundException);
    });
  });

  describe('deleteSummaryById', () => {
    it('should delete summary successfully', async () => {
      const stateId = 'test-state-123';
      const result = await controller.deleteSummaryById({ stateId });

      expect(result).toEqual({ message: 'State deleted successfully' });
      expect(stateService.exists).toHaveBeenCalledWith(stateId);
      expect(summaryService.removeSummary).toHaveBeenCalledWith(stateId);
    });

    it('should throw NotFoundException when state does not exist', async () => {
      stateService.exists.mockReturnValueOnce(false);
      const stateId = 'non-existent-state';

      await expect(controller.deleteSummaryById({ stateId }))
        .rejects.toThrow(NotFoundException);
    });

    it('should handle removal service errors', async () => {
      summaryService.removeSummary.mockRejectedValueOnce(new Error('Removal failed'));
      const stateId = 'test-state-123';

      await expect(controller.deleteSummaryById({ stateId }))
        .rejects.toThrow('Removal failed');
    });
  });

  describe('edge cases and error handling', () => {
    it('should handle empty states array', () => {
      stateService.fetchAll.mockReturnValueOnce([]);

      const result = controller.getSummary();
      expect(result).toEqual([]);
    });

    it('should handle service errors gracefully', async () => {
      videoService.getVideo.mockRejectedValueOnce(new Error('Video service error'));

      await expect(controller.startSummaryPipeline({
        title: 'Test',
        videoId: 'test',
        sampling: { 
          chunkDuration: 10,
          samplingFrame: 1,
          frameOverlap: 1,
          multiFrame: 2
        },
        evam: { evamPipeline: EVAMPipelines.OBJECT_DETECTION }
      })).rejects.toThrow('Video service error');
    });
  });
});
