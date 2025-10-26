// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Test, TestingModule } from '@nestjs/testing';
import { PipelineService } from './pipeline.service';
import { StateService } from './state.service';
import { DatastoreService } from 'src/datastore/services/datastore.service';
import { LocalstoreService } from 'src/datastore/services/localstore.service';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { EvamService } from 'src/evam/services/evam.service';
import { AudioService } from 'src/audio/services/audio.service';
import { ChunkingService } from '../queues/chunking.service';
import { AudioQueueService } from '../queues/audio-queue.service';
import { StateActionStatus } from '../models/state.model';
import { PipelineEvents } from 'src/events/Pipeline.events';
import { of } from 'rxjs';

describe('PipelineService', () => {
  let service: PipelineService;
  let stateService: jest.Mocked<Partial<StateService>>;
  let datastoreService: jest.Mocked<DatastoreService>;
  let localstoreService: jest.Mocked<LocalstoreService>;
  let eventEmitter: jest.Mocked<Partial<EventEmitter2>>;
  let evamService: jest.Mocked<EvamService>;
  let audioService: jest.Mocked<AudioService>;
  let chunkingService: jest.Mocked<ChunkingService>;
  let audioQueueService: jest.Mocked<AudioQueueService>;
  const mockStateId = 'test-state-id';
  const mockStates = ['state-1', 'state-2'];

  beforeEach(async () => {
    // Create mock implementations for all dependencies
    const mockStateService = {
      fetch: jest.fn(),
      updateChunkingStatus: jest.fn(),
      updateDataStoreUploadStatus: jest.fn(),
      updateDatastoreVideoURI: jest.fn(),
      addEVAMInferenceConfig: jest.fn(),
      updateEVAM: jest.fn(),
      addChunk: jest.fn(),
      updateFrameSummary: jest.fn(),
      updateSummaryStatus: jest.fn(),
      addSummaryStream: jest.fn(),
      summaryComplete: jest.fn(),
    };

    const mockDatastoreService = {
      getObjectName: jest.fn(),
      uploadFile: jest.fn(),
      getObjectURL: jest.fn(),
      getObjectRelativePath: jest.fn(),
    };

    const mockLocalstoreService = {};

    const mockEventEmitter = {
      emit: jest.fn(),
    };

    const mockEvamService = {
      startChunkingStub: jest.fn(),
      getVideoTimeStamp: jest.fn(),
      getInferenceConfig: jest.fn(),
      addStateToProgress: jest.fn(),
      isChunkingInProgress: jest.fn(),
    };

    const mockAudioService = {};

    const mockChunkingService = {
      hasProcessing: jest.fn(),
    };

    const mockAudioQueueService = {
      isAudioProcessing: jest.fn(),
    };

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        PipelineService,
        { provide: StateService, useValue: mockStateService },
        { provide: DatastoreService, useValue: mockDatastoreService },
        { provide: LocalstoreService, useValue: mockLocalstoreService },
        { provide: EventEmitter2, useValue: mockEventEmitter },
        { provide: EvamService, useValue: mockEvamService },
        { provide: AudioService, useValue: mockAudioService },
        { provide: ChunkingService, useValue: mockChunkingService },
        { provide: AudioQueueService, useValue: mockAudioQueueService },
      ],
    }).compile();

    service = module.get<PipelineService>(PipelineService);
    stateService = module.get(StateService) as jest.Mocked<StateService>;
    datastoreService = module.get(
      DatastoreService,
    ) as jest.Mocked<DatastoreService>;
    localstoreService = module.get(
      LocalstoreService,
    ) as jest.Mocked<LocalstoreService>;
    eventEmitter = module.get(EventEmitter2) as jest.Mocked<EventEmitter2>;
    evamService = module.get(EvamService) as jest.Mocked<EvamService>;
    audioService = module.get(AudioService) as jest.Mocked<AudioService>;
    chunkingService = module.get(
      ChunkingService,
    ) as jest.Mocked<ChunkingService>;
    audioQueueService = module.get(
      AudioQueueService,
    ) as jest.Mocked<AudioQueueService>;
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  describe('chunkingComplete', () => {
    it('should update chunking status to COMPLETE for all state IDs', async () => {
      // Act
      await service.chunkingComplete(mockStates);

      // Assert
      expect(stateService.updateChunkingStatus).toHaveBeenCalledTimes(
        mockStates.length,
      );
      mockStates.forEach((stateId) => {
        expect(stateService.updateChunkingStatus).toHaveBeenCalledWith(
          stateId,
          StateActionStatus.COMPLETE,
        );
      });
    });
  });

  describe('checkQueueStatus', () => {
    it('should emit CHUNKING_COMPLETE event when states are not in progress', async () => {
      // Arrange
      evamService.isChunkingInProgress!.mockImplementation(
        (stateId) => stateId === 'state-2',
      );
      audioQueueService.isAudioProcessing.mockReturnValue(false);

      // Act
      await service.checkQueueStatus(mockStates);

      // Assert
      expect(evamService.isChunkingInProgress).toHaveBeenCalledTimes(2);
      expect(audioQueueService.isAudioProcessing).toHaveBeenCalledTimes(1);
      expect(eventEmitter.emit).toHaveBeenCalledWith(
        PipelineEvents.CHUNKING_COMPLETE,
        ['state-1'],
      );
    });

    it('should not emit CHUNKING_COMPLETE event when all states are in progress', async () => {
      // Arrange
      evamService.isChunkingInProgress.mockReturnValue(true);
      audioQueueService.isAudioProcessing.mockReturnValue(false);

      // Act
      await service.checkQueueStatus(mockStates);

      // Assert
      expect(eventEmitter.emit).not.toHaveBeenCalled();
    });

    it('should filter states that are either in evam or audio queue', async () => {
      // Arrange
      evamService.isChunkingInProgress.mockImplementation(
        (stateId) => stateId === 'state-1',
      );
      audioQueueService.isAudioProcessing.mockImplementation(
        (stateId) => stateId === 'state-2',
      );

      // Act
      await service.checkQueueStatus(mockStates);

      // Assert
      expect(eventEmitter.emit).not.toHaveBeenCalled();
    });
  });

  describe('chunkingTriggered', () => {
    it('should update chunking status to IN_PROGRESS', () => {
      // Act
      service.chunkingTriggered({ stateId: mockStateId });

      // Assert
      expect(stateService.updateChunkingStatus).toHaveBeenCalledWith(
        mockStateId,
        StateActionStatus.IN_PROGRESS,
      );
    });
  });

  describe('triggerChunking', () => {
    const mockState = {
      video: { 
        dataStore: true, 
        url: 'test-video-url' 
      },
      userInputs: { prompt: 'test prompt' },
      systemConfig: { 
        evamPipeline: 'test-pipeline',
        audioModel: 'test-audio-model'
      }
    };

    it('should trigger chunking and audio when state exists with audio model', async () => {
      // Arrange
      (stateService.fetch as jest.Mock).mockReturnValue(mockState);
      datastoreService.getObjectURL.mockReturnValue('https://test-url.com/video');
      const mockResponse = { 
        data: { pipelineId: 'test-pipeline-123' },
        status: 200,
        statusText: 'OK',
        headers: {},
        config: { headers: {} }
      } as any;
      evamService.startChunkingStub.mockReturnValue(of(mockResponse));
      evamService.getInferenceConfig.mockReturnValue({ 
        model: 'test-model', 
        device: 'cpu' 
      });

      // Act
      await service.triggerChunking(mockStateId);

      // Assert
      expect(stateService.fetch).toHaveBeenCalledWith(mockStateId);
      expect(datastoreService.getObjectURL).toHaveBeenCalledWith('test-video-url');
      expect(eventEmitter.emit).toHaveBeenCalledWith(
        PipelineEvents.CHUNKING_TRIGGERED,
        { stateId: mockStateId }
      );
      expect(eventEmitter.emit).toHaveBeenCalledWith(
        PipelineEvents.AUDIO_TRIGGERED,
        mockStateId
      );
      expect(evamService.startChunkingStub).toHaveBeenCalledWith(
        mockStateId,
        'https://test-url.com/video',
        mockState.userInputs,
        mockState.systemConfig.evamPipeline
      );
      expect(stateService.addEVAMInferenceConfig).toHaveBeenCalledWith(
        mockStateId,
        { model: 'test-model', device: 'cpu' }
      );
      expect(evamService.addStateToProgress).toHaveBeenCalledWith(
        mockStateId,
        mockResponse.data
      );
      expect(stateService.updateEVAM).toHaveBeenCalledWith(
        mockStateId,
        mockResponse.data
      );
    });

    it('should trigger chunking without audio when no audio model configured', async () => {
      // Arrange
      const mockStateNoAudio = {
        ...mockState,
        systemConfig: { evamPipeline: 'test-pipeline' }
      };
      (stateService.fetch as jest.Mock).mockReturnValue(mockStateNoAudio);
      datastoreService.getObjectURL.mockReturnValue('https://test-url.com/video');
      const mockResponse = { 
        data: { pipelineId: 'test-pipeline-123' },
        status: 200,
        statusText: 'OK',
        headers: {},
        config: { headers: {} }
      } as any;
      evamService.startChunkingStub.mockReturnValue(of(mockResponse));
      evamService.getInferenceConfig.mockReturnValue({ 
        model: 'test-model', 
        device: 'cpu' 
      });

      // Act
      await service.triggerChunking(mockStateId);

      // Assert
      expect(eventEmitter.emit).toHaveBeenCalledWith(
        PipelineEvents.CHUNKING_TRIGGERED,
        { stateId: mockStateId }
      );
      expect(eventEmitter.emit).not.toHaveBeenCalledWith(
        PipelineEvents.AUDIO_TRIGGERED,
        mockStateId
      );
    });

    it('should not trigger chunking when state does not exist', async () => {
      // Arrange
      (stateService.fetch as jest.Mock).mockReturnValue(null);

      // Act
      await service.triggerChunking(mockStateId);

      // Assert
      expect(stateService.fetch).toHaveBeenCalledWith(mockStateId);
      expect(datastoreService.getObjectURL).not.toHaveBeenCalled();
      expect(eventEmitter.emit).not.toHaveBeenCalled();
    });

    it('should not trigger chunking when dataStore is false', async () => {
      // Arrange
      const mockStateNoDataStore = {
        ...mockState,
        video: { dataStore: false, url: 'test-video-url' }
      };
      (stateService.fetch as jest.Mock).mockReturnValue(mockStateNoDataStore);

      // Act
      await service.triggerChunking(mockStateId);

      // Assert
      expect(datastoreService.getObjectURL).not.toHaveBeenCalled();
      expect(eventEmitter.emit).not.toHaveBeenCalled();
    });

    it('should handle errors during chunking trigger', async () => {
      // Arrange
      (stateService.fetch as jest.Mock).mockReturnValue(mockState);
      datastoreService.getObjectURL.mockReturnValue('https://test-url.com/video');
      evamService.startChunkingStub.mockReturnValue({ 
        subscribe: jest.fn(),
        pipe: jest.fn().mockReturnThis()
      } as any);
      
      const consoleSpy = jest.spyOn(console, 'log').mockImplementation();
      const error = new Error('EVAM service error');
      evamService.startChunkingStub.mockImplementation(() => {
        throw error;
      });

      // Act
      await service.triggerChunking(mockStateId);

      // Assert
      expect(consoleSpy).toHaveBeenCalledWith('ERROR MESSAGE', error.message);
      
      consoleSpy.mockRestore();
    });
  });

  describe('triggerChunkCaptioning', () => {
    const mockChunkData = {
      evamIdentifier: mockStateId,
      chunkId: 123,
      frames: [
        { frameId: 'frame-1', imageUri: 'frame1.jpg' },
        { frameId: 'frame-2', imageUri: 'frame2.jpg' }
      ]
    };

    it('should add chunk to state', async () => {
      // Act
      await service.triggerChunkCaptioning(mockChunkData);

      // Assert
      expect(stateService.addChunk).toHaveBeenCalledWith(
        mockStateId,
        mockChunkData
      );
    });
  });

  describe('frameCaptionProgress', () => {
    const mockPayload = {
      stateId: mockStateId,
      frameIds: ['frame-1', 'frame-2'],
      caption: 'test caption'
    };

    it('should update frame summary status to IN_PROGRESS', () => {
      // Act
      service.frameCaptionProgress(mockPayload);

      // Assert
      const expectedFrameKey = mockPayload.frameIds.join('#');
      expect(stateService.updateFrameSummary).toHaveBeenCalledWith(
        mockStateId,
        expectedFrameKey,
        StateActionStatus.IN_PROGRESS
      );
    });
  });

  describe('updateFrameCaption', () => {
    const mockPayload = {
      stateId: mockStateId,
      frameIds: ['frame-1', 'frame-2'],
      caption: 'Test caption content'
    };

    it('should update frame summary with caption and COMPLETE status', () => {
      // Act
      service.updateFrameCaption(mockPayload);

      // Assert
      const expectedFrameKey = mockPayload.frameIds.join('#');
      expect(stateService.updateFrameSummary).toHaveBeenCalledWith(
        mockStateId,
        expectedFrameKey,
        StateActionStatus.COMPLETE,
        mockPayload.caption
      );
    });
  });

  describe('summaryTrigger', () => {
    it('should update summary status to READY', () => {
      // Act
      service.summaryTrigger({ stateId: mockStateId });

      // Assert
      expect(stateService.updateSummaryStatus).toHaveBeenCalledWith(
        mockStateId,
        StateActionStatus.READY
      );
    });
  });

  describe('summaryProcessing', () => {
    it('should update summary status to IN_PROGRESS', () => {
      // Act
      service.summaryProcessing({ stateId: mockStateId });

      // Assert
      expect(stateService.updateSummaryStatus).toHaveBeenCalledWith(
        mockStateId,
        StateActionStatus.IN_PROGRESS
      );
    });
  });

  describe('summaryStream', () => {
    const mockSummaryStreamData = {
      stateId: mockStateId,
      streamChunk: 'This is a stream chunk of summary content...'
    };

    it('should add summary stream chunk to state', () => {
      // Act
      service.summaryStream(mockSummaryStreamData);

      // Assert
      expect(stateService.addSummaryStream).toHaveBeenCalledWith(
        mockStateId,
        mockSummaryStreamData.streamChunk
      );
    });
  });

  describe('summaryComplete', () => {
    const mockSummaryCompleteData = {
      stateId: mockStateId,
      summary: 'Final complete summary of the video content.'
    };

    it('should complete summary and log completion', () => {
      // Arrange
      const consoleSpy = jest.spyOn(console, 'log').mockImplementation();

      // Act
      service.summaryComplete(mockSummaryCompleteData);

      // Assert
      expect(stateService.summaryComplete).toHaveBeenCalledWith(
        mockStateId,
        mockSummaryCompleteData.summary
      );
      expect(consoleSpy).toHaveBeenCalledWith(
        ' SUMMARY COMPLETE PIPELINE',
        mockStateId,
        mockSummaryCompleteData.summary
      );

      consoleSpy.mockRestore();
    });
  });
});
