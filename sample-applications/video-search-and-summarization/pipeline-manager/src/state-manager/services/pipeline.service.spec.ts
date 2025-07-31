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
});
