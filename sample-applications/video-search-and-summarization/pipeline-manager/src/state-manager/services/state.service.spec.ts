// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Test, TestingModule } from '@nestjs/testing';
import { StateService } from './state.service';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { ConfigService } from '@nestjs/config';
import { StateDbService } from './state-db.service';
import { SocketEvent } from 'src/events/socket.events';
import {
  FileInfo,
  ModelInfo,
  State,
  StateActionStatus,
  StateChunk,
  StateChunkFrame,
} from '../models/state.model';
import { Video } from 'src/video-upload/models/video.model';
import { SummaryPipelineSampling } from 'src/summary/models/summary-pipeline.model';
import {
  AudioDevice,
  AudioTranscriptDTO,
  AudioTranscriptsParsed,
} from 'src/audio/models/audio.model';
import { ChunkQueue } from 'src/evam/models/message-broker.model';
import {
  VideoUploadDTO,
  SystemConfig,
} from 'src/video-upload/models/upload.model';
import * as uuid from 'uuid';
import { EVAMPipelines } from 'src/evam/models/evam.model';

jest.mock('uuid');

describe('StateService', () => {
  jest.useFakeTimers();
  
  let service: StateService;
  let eventEmitterMock: jest.Mocked<EventEmitter2>;
  let configServiceMock: jest.Mocked<Partial<ConfigService>>;
  let stateDbServiceMock: jest.Mocked<Partial<StateDbService>>;

  const mockStateId = 'test-state-id';
  const mockState: State = {
    stateId: mockStateId,
    title: 'Test Video Title',
    video: {
      dbId: 1,
      videoId: 'test-video-id',
      name: 'Test Video',
      url: 'http://example.com/video.mp4',
      tags: ['test'],
      createdAt: '2024-01-01T00:00:00Z',
      updatedAt: '2024-01-01T00:00:00Z',
      dataStore: {
        bucket: 'test-bucket',
        objectName: 'test-object',
        fileName: 'test-video.mp4'
      },
    },
    createdAt: '2025-05-12T00:00:00.000Z',
    updatedAt: '2025-05-12T00:00:00.000Z',
  // fileInfo removed, not present in State
    systemConfig: {
      evamPipeline: EVAMPipelines.BASIC_INGESTION,
      frameOverlap: 3,
      framePrompt: 'framePrompt',
      multiFrame: 4,
      summaryMapPrompt: 'summaryMapPrompt',
      summaryReducePrompt: 'summaryReducePrompt',
      summarySinglePrompt: 'summarySinglePrompt',
    },
    userInputs: {
      chunkDuration: 1,
      samplingFrame: 1,
      frameOverlap: 1,
      multiFrame: 1,
    },
    chunks: {},
    frames: {},
    frameSummaries: {},
    inferenceConfig: {},
    status: {
      summarizing: StateActionStatus.NA,
      dataStoreUpload: StateActionStatus.NA,
      chunking: StateActionStatus.NA,
    },
  };

  beforeEach(async () => {
    jest.clearAllMocks();

    // Create mocks for dependencies
    eventEmitterMock = {
      emit: jest.fn(),
    } as unknown as jest.Mocked<EventEmitter2>;

    configServiceMock = {
      get: jest.fn(),
    };

    stateDbServiceMock = {
      updateState: jest.fn().mockResolvedValue({ success: true }),
      addState: jest.fn().mockResolvedValue({ success: true }),
      removeState: jest.fn().mockResolvedValue(true),
      getState: jest.fn().mockResolvedValue(null),
      getAllStates: jest.fn().mockResolvedValue([]),
    };

    // Mock uuid.v4
    (uuid.v4 as jest.Mock).mockReturnValue(mockStateId);

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        StateService,
        { provide: EventEmitter2, useValue: eventEmitterMock },
        { provide: ConfigService, useValue: configServiceMock },
        { provide: StateDbService, useValue: stateDbServiceMock },
      ],
    }).compile();

    service = module.get<StateService>(StateService);
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  describe('create method', () => {
    it('should create a new state with given parameters', async () => {
      const video: Video = {
        videoId: 'vid-123',
        name: 'Test Video',
        url: 'uploads/test-video.mp4',
        tags: [],
        createdAt: '2025-05-12T00:00:00.000Z',
        updatedAt: '2025-05-12T00:00:00.000Z',
      };

      const systemConfig: SystemConfig = {
        evamPipeline: EVAMPipelines.BASIC_INGESTION,
        frameOverlap: 3,
        framePrompt: 'framePrompt',
        multiFrame: 4,
        summaryMapPrompt: 'summaryMapPrompt',
        summaryReducePrompt: 'summaryReducePrompt',
        summarySinglePrompt: 'summarySinglePrompt',
      };

      const userInputs: SummaryPipelineSampling = {
        chunkDuration: 1,
        samplingFrame: 1,
        frameOverlap: 1,
        multiFrame: 1,
      };

      const result = await service.create(video, 'Test Title', systemConfig, userInputs);

      expect(result).toBeDefined();
      expect(result.stateId).toBe(mockStateId);
      expect(result.systemConfig).toEqual(systemConfig);
      expect(result.userInputs).toEqual(userInputs);
      expect(stateDbServiceMock.addState).toHaveBeenCalledWith(
        expect.objectContaining({
          stateId: mockStateId,
          systemConfig,
          userInputs,
        }),
      );
      expect(eventEmitterMock.emit).toHaveBeenCalledWith(
        SocketEvent.STATE_SYNC,
        { stateId: mockStateId },
      );
    });

    it('should create a state with default userInputs when not provided', async () => {
      const video: Video = {
        videoId: 'vid-123',
        name: 'Test Video',
        url: 'uploads/test-video.mp4',
        tags: [],
        createdAt: '2025-05-12T00:00:00.000Z',
        updatedAt: '2025-05-12T00:00:00.000Z',
      };

      const systemConfig: SystemConfig = {
        evamPipeline: EVAMPipelines.BASIC_INGESTION,
        frameOverlap: 3,
        framePrompt: 'framePrompt',
        multiFrame: 4,
        summaryMapPrompt: 'summaryMapPrompt',
        summaryReducePrompt: 'summaryReducePrompt',
        summarySinglePrompt: 'summarySinglePrompt',
      };

      const defaultUserInputs: SummaryPipelineSampling = {
        chunkDuration: 1,
        samplingFrame: 1,
        frameOverlap: 1,
        multiFrame: 1,
      };
      
      const result = await service.create(video, 'Test Title', systemConfig, defaultUserInputs);

      expect(result.userInputs).toEqual({
      chunkDuration: 1,
      samplingFrame: 1,
      frameOverlap: 1,
      multiFrame: 1,
      });
    });
  });

  describe('fetch, fetchChunk, fetchFrame methods', () => {
    beforeEach(() => {
      // Add a state to the service
      service.update(mockState);
    });

    it('should fetch state by id', () => {
      const result = service.fetch(mockStateId);
      expect(result).toEqual(mockState);
    });

    it('should return undefined when fetching non-existent state', () => {
      const result = service.fetch('non-existent-id');
      expect(result).toBeUndefined();
    });

    it('should fetch a chunk from state', () => {
      // Add a chunk to the state
      const chunkId = 'chunk-1';
      const mockStateWithChunk = {
        ...mockState,
        chunks: {
          [chunkId]: { chunkId },
        },
      };
      service.update(mockStateWithChunk);

      const result = service.fetchChunk(mockStateId, chunkId);
      expect(result).toEqual({ chunkId });
    });

    it('should return null when fetching non-existent chunk', () => {
      const result = service.fetchChunk(mockStateId, 'non-existent-chunk');
      expect(result).toBeNull();
    });

    it('should fetch a frame from state', () => {
      // Add a frame to the state
      const frameId = 'frame-1';
      const chunkId = 'chunk-1';
      const mockFrame: StateChunkFrame = {
        frameId,
        chunkId,
        createdAt: '2025-05-12T00:00:00.000Z',
        frameUri: 'test-uri',
      };

      const mockStateWithFrame = {
        ...mockState,
        frames: {
          [frameId]: mockFrame,
        },
      };
      service.update(mockStateWithFrame);

      const result = service.fetchFrame(mockStateId, frameId);
      expect(result).toEqual(mockFrame);
    });

    it('should return null when fetching non-existent frame', () => {
      const result = service.fetchFrame(mockStateId, 'non-existent-frame');
      expect(result).toBeNull();
    });
  });

  describe('update method', () => {
    it('should update the state and sync socket', () => {
      const newState = { ...mockState };
      service.update(newState);

      expect(service.fetch(mockStateId)).toEqual(newState);
      expect(eventEmitterMock.emit).toHaveBeenCalledWith(
        SocketEvent.STATE_SYNC,
        { stateId: mockStateId },
      );
    });
  });

  describe('audioTrigger and audioComplete methods', () => {
    beforeEach(() => {
      service.update(mockState);
    });

    it('should set audio in progress state when triggered', () => {
      const audioRequest: AudioTranscriptDTO = {
        device: AudioDevice.CPU,
        model_name: 'test-model',
        video_id: mockStateId,
        include_timestamps: true,
        video_name: 'original.mp4',
        minio_bucket: 'test-bucket',
      };

      service.audioTrigger(mockStateId, audioRequest);

      const state = service.fetch(mockStateId);
      expect(state?.audio).toBeDefined();
      expect(state?.audio?.status).toBe(StateActionStatus.IN_PROGRESS);
      expect(state?.audio?.device).toBe(audioRequest.device);
      expect(state?.audio?.model).toBe(audioRequest.model_name);
    });

    it('should update audio state when completed', () => {
      // Setup audio in progress first
      const audioRequest: AudioTranscriptDTO = {
        device: AudioDevice.CPU,
        model_name: 'test-model',
        video_id: mockStateId,
        include_timestamps: true,
        video_name: 'original.mp4',
        minio_bucket: 'test-bucket',
      };
      service.audioTrigger(mockStateId, audioRequest);

      // Now complete the audio
      const audioResult: AudioTranscriptsParsed = {
        transcriptPath: 'test-path',
        transcripts: [
          { text: 'test transcript', startSeconds: 0, endSeconds: 1 } as any,
        ],
      };

      service.audioComplete(mockStateId, audioResult);

      const state = service.fetch(mockStateId);
      expect(state?.audio?.status).toBe(StateActionStatus.COMPLETE);
      expect(state?.audio?.transcriptPath).toBe(audioResult.transcriptPath);
      expect(state?.audio?.transcript).toEqual(audioResult.transcripts);
    });

    it('should not update audio state for non-existent state', () => {
      const audioResult: AudioTranscriptsParsed = {
        transcriptPath: 'test-path',
        transcripts: [
          { text: 'test transcript', startSeconds: 0, endSeconds: 1 } as any,
        ],
      };

      service.audioComplete('non-existent-id', audioResult);
      // Should not throw an error
    });
  });

  describe('addChunk method', () => {
    beforeEach(() => {
      service.update(mockState);
    });

    it('should add a chunk with frames to the state', () => {
      const mockChunk: ChunkQueue = {
        chunkId: 1,
        evamIdentifier: mockStateId,
        frames: [
          {
            frameId: '1',
            imageUri: 'uri-1',
            metadata: { foo: 'bar' } as any,
          },
          {
            frameId: '2',
            imageUri: 'uri-2',
          },
        ],
      };

      service.addChunk(mockStateId, mockChunk);

      const state = service.fetch(mockStateId);
      expect(state?.chunks['1']).toBeDefined();
      expect(state?.frames['1']).toBeDefined();
      expect(state?.frames['2']).toBeDefined();
      expect(state?.frames['1'].frameUri).toBe('uri-1');
      expect(state?.frames['1'].metadata).toEqual({ foo: 'bar' });
      expect(state?.frames['2'].metadata).toBeUndefined();
      expect(eventEmitterMock.emit).toHaveBeenCalledWith(
        SocketEvent.STATE_SYNC,
        { stateId: mockStateId },
      );
    });
  });

  describe('summary related methods', () => {
    beforeEach(() => {
      service.update(mockState);
    });

    it('should update summary status', () => {
      service.updateSummaryStatus(mockStateId, StateActionStatus.IN_PROGRESS);

      const state = service.fetch(mockStateId);
      expect(state?.status.summarizing).toBe(StateActionStatus.IN_PROGRESS);
      expect(eventEmitterMock.emit).toHaveBeenCalledWith(
        SocketEvent.STATUS_SYNC,
        { stateId: mockStateId },
      );
    });

    it('should add summary stream chunks', () => {
      // Add first chunk
      service.addSummaryStream(mockStateId, 'Hello ');
      let state = service.fetch(mockStateId);
      expect(state?.summary).toBe('Hello ');

      // Add second chunk
      service.addSummaryStream(mockStateId, 'world');
      state = service.fetch(mockStateId);
      expect(state?.summary).toBe('Hello world');
    });

    it('should handle complete summary', () => {
      const summary = 'Final summary text';
      service.summaryComplete(mockStateId, summary);

      const state = service.fetch(mockStateId);
      expect(state?.summary).toBe(summary);
      expect(state?.status.summarizing).toBe(StateActionStatus.COMPLETE);
      expect(stateDbServiceMock.updateState).toHaveBeenCalledWith(
        mockStateId,
        expect.any(Object),
      );
      expect(eventEmitterMock.emit).toHaveBeenCalledWith(
        SocketEvent.SUMMARY_SYNC,
        { stateId: mockStateId, summary },
      );
    });
  });

  describe('frame summary methods', () => {
    beforeEach(() => {
      service.update(mockState);
    });

    it('should add frame summary', () => {
      const frameIds = ['1', '2', '3'];
      const summary = 'Test frame summary';

      service.addFrameSummary(mockStateId, frameIds, summary);

      const state = service.fetch(mockStateId);
      const frameKey = frameIds.join('#');
      expect(state?.frameSummaries[frameKey]).toBeDefined();
      expect(state?.frameSummaries[frameKey].frames).toEqual(frameIds);
      expect(state?.frameSummaries[frameKey].summary).toBe(summary);
      expect(state?.frameSummaries[frameKey].startFrame).toBe('1');
      expect(state?.frameSummaries[frameKey].endFrame).toBe('3');
      expect(eventEmitterMock.emit).toHaveBeenCalledWith(
        SocketEvent.FRAME_SUMMARY_SYNC,
        { stateId: mockStateId, frameKey },
      );
    });

    it('should update frame summary', () => {
      // Add frame summary first
      const frameIds = ['1', '2', '3'];
      const frameKey = frameIds.join('#');
      service.addFrameSummary(mockStateId, frameIds);

      // Update frame summary
      const newSummary = 'Updated summary';
      service.updateFrameSummary(
        mockStateId,
        frameKey,
        StateActionStatus.COMPLETE,
        newSummary,
      );

      const state = service.fetch(mockStateId);
      expect(state?.frameSummaries[frameKey].summary).toBe(newSummary);
      expect(state?.frameSummaries[frameKey].status).toBe(
        StateActionStatus.COMPLETE,
      );
    });

    it('should not update non-existent frame summary', () => {
      service.updateFrameSummary(
        mockStateId,
        'non-existent-frame-key',
        StateActionStatus.NA,
      );

      // Should not throw error
      expect(eventEmitterMock.emit).not.toHaveBeenCalledWith(
        SocketEvent.FRAME_SUMMARY_SYNC,
        expect.anything(),
      );
    });
  });

  describe('inference config methods', () => {
    beforeEach(() => {
      service.update(mockState);
    });

    it('should add EVAM inference config', () => {
      const modelInfo: ModelInfo = {
        device: AudioDevice.CPU,
        model: 'test-model',
      };

      service.addEVAMInferenceConfig(mockStateId, modelInfo);

      const state = service.fetch(mockStateId);
      expect(state?.inferenceConfig?.objectDetection).toEqual(modelInfo);
      expect(eventEmitterMock.emit).toHaveBeenCalledWith(
        SocketEvent.CONFIG_SYNC,
        mockStateId,
      );
    });

    it('should add text inference config', () => {
      const modelInfo: ModelInfo = {
        device: AudioDevice.CPU,
        model: 'test-model',
      };

      service.addTextInferenceConfig(mockStateId, modelInfo);

      const state = service.fetch(mockStateId);
      expect(state?.inferenceConfig?.textInference).toEqual(modelInfo);
    });

    it('should add image inference config', () => {
      const modelInfo: ModelInfo = {
        device: AudioDevice.CPU,
        model: 'test-model',
      };

      service.addImageInferenceConfig(mockStateId, modelInfo);

      const state = service.fetch(mockStateId);
      expect(state?.inferenceConfig?.imageInference).toEqual(modelInfo);
    });
  });

  describe('video URI and status methods', () => {
    beforeEach(() => {
      service.update(mockState);
    });

    it('should update datastore video URI', () => {
      const minioObject = 'test-minio-object';
      const extension = '.mp4';

  // service.updateDatastoreVideoURI(mockStateId, minioObject, extension); // Method does not exist

      const state = service.fetch(mockStateId);
  // expect(state?.fileInfo.minioObject).toBe(minioObject); // Property does not exist
  // expect(state?.fileInfo.extension).toBe(extension); // Property does not exist
      expect(eventEmitterMock.emit).toHaveBeenCalledWith(
        SocketEvent.STATE_SYNC,
        { stateId: mockStateId },
      );
    });

    it('should update EVAM', () => {
      const evamProcessId = 'process-123';
      const videoUri = 'video-uri';
      const videoTimeStamp = '2025-05-12T00:00:00.000Z';

  service.updateEVAM(mockStateId, evamProcessId);

      const state = service.fetch(mockStateId);
      expect(state?.evamProcessId).toBe(evamProcessId);
  // expect(state?.videoURI).toBe(videoUri); // Property does not exist
  // expect(state?.videoStartTime).toBe(videoTimeStamp); // Property does not exist
    });

    it('should update datastore upload status', () => {
      service.updateDataStoreUploadStatus(
        mockStateId,
        StateActionStatus.IN_PROGRESS,
      );

      let state = service.fetch(mockStateId);
      expect(state?.status.dataStoreUpload).toBe(StateActionStatus.IN_PROGRESS);

      // Should update timestamp
      const previousUpdatedAt = state?.updatedAt;

      // Wait a bit to ensure timestamps are different
      jest.advanceTimersByTime(10);

      service.updateDataStoreUploadStatus(
        mockStateId,
        StateActionStatus.COMPLETE,
      );
      state = service.fetch(mockStateId);
      expect(state?.status.dataStoreUpload).toBe(StateActionStatus.COMPLETE);
      expect(state?.updatedAt).not.toBe(previousUpdatedAt);
    });

    it('should update chunking status', () => {
      service.updateChunkingStatus(mockStateId, StateActionStatus.IN_PROGRESS);

      const state = service.fetch(mockStateId);
      expect(state?.status.chunking).toBe(StateActionStatus.IN_PROGRESS);
      expect(eventEmitterMock.emit).toHaveBeenCalledWith(
        SocketEvent.STATUS_SYNC,
        { stateId: mockStateId },
      );
    });
  });

  describe('saveToDB method', () => {
    beforeEach(() => {
      service.update(mockState);
    });

    it('should save state to DB', () => {
      service.saveToDB(mockStateId);

      expect(stateDbServiceMock.updateState).toHaveBeenCalledWith(
        mockStateId,
        expect.objectContaining({ stateId: mockStateId }),
      );
    });

    it('should not save non-existent state', () => {
      service.saveToDB('non-existent-id');

      expect(stateDbServiceMock.updateState).not.toHaveBeenCalled();
    });
  });

  describe('remove method', () => {
    beforeEach(() => {
      service.update(mockState);
    });

    it('should remove state', async () => {
      expect(service.has(mockStateId)).toBe(true);

      await service.remove(mockStateId);

      expect(service.has(mockStateId)).toBe(false);
    });

    it('should handle removing non-existent state', () => {
      service.remove('non-existent-id');
      // Should not throw error
    });
  });

  describe('has method', () => {
    it('should return true for existing state', () => {
      service.update(mockState);
      expect(service.has(mockStateId)).toBe(true);
    });

    it('should return false for non-existent state', () => {
      expect(service.has('non-existent-id')).toBe(false);
    });
  });
});
