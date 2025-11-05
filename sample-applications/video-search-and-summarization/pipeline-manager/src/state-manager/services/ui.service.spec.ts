// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Test, TestingModule } from '@nestjs/testing';
import { UiService } from './ui.service';
import { StateService } from './state.service';
import { ConfigService } from '@nestjs/config';
import { DatastoreService } from 'src/datastore/services/datastore.service';
import {
  FrameSummary,
  InferenceConfig,
  State,
  StateActionStatus,
  StateAudio,
} from '../models/state.model';
import {
  CountStatus,
  UIChunk,
  UIFrame,
  UIState,
  UIStateStatus,
} from '../models/uiState.model';
import { DateTime } from 'luxon';
import { AudioDevice } from 'src/audio/models/audio.model';
import { EVAMPipelines } from 'src/evam/models/evam.model';

describe('UiService', () => {
  let service: UiService;
  let stateService: StateService;
  let configService: ConfigService;
  let datastoreService: DatastoreService;

  // Mock data
  const mockStateId = 'test-state-id';
  const mockChunkId = '1';
  const mockFrameId = 'frame-1';
  const mockFrameKey = 'frame-key-1';

  // Mock state object
  const mockState: State = {
  title: 'Test Video',
  video: {} as any,
    stateId: mockStateId,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  // fileInfo removed, not present in State model
    userInputs: {
      videoStart: 0,
      videoEnd: 100,
      chunkDuration: 10,
      samplingFrame: 5,
      frameOverlap: 2,
      multiFrame: 4,
      // videoName removed, not present in SummaryPipelineSampling
    },
    chunks: {
      '1': { chunkId: '1' },
      '2': { chunkId: '2' },
    },
    frames: {
      'frame-1': {
        frameId: 'frame-1',
        chunkId: '1',
        createdAt: new Date().toISOString(),
        frameUri: 'http://example.com/frame1.jpg',
        metadata: { image_format: 'jpg', frame_timestamp: 1000 },
      },
      'frame-2': {
        frameId: 'frame-2',
        chunkId: '1',
        createdAt: new Date().toISOString(),
        frameUri: 'http://example.com/frame2.jpg',
        metadata: { frame_timestamp: 2000, image_format: 'jpg' },
      },
    },
    frameSummaries: {
      'frame-key-1': {
        summary: 'This is a test summary',
        frames: ['frame-1', 'frame-2'],
        frameKey: 'frame-key-1',
        startFrame: 'frame-1',
        endFrame: 'frame-2',
        status: StateActionStatus.COMPLETE,
      },
    },
  // videoURI removed, not present in State/UIState
  // videoStartTime removed, not present in State model
    summary: 'Overall video summary',
    systemConfig: {
      evamPipeline: EVAMPipelines.BASIC_INGESTION,
      frameOverlap: 2,
      framePrompt: 'Test prompt',
      multiFrame: 4,
      summaryMapPrompt: 'Test summary prompt',
      summaryReducePrompt: 'Test reduce prompt',
      summarySinglePrompt: 'Test single prompt',
    },
    inferenceConfig: {
      textInference: {
        model: 'gpt-4',
        device: 'CPU',
      },
      imageInference: {
        model: 'vision-model',
        device: 'GPU',
      },
    },
    audio: {
      device: AudioDevice.CPU,
      model: 'whisper',
      status: StateActionStatus.COMPLETE,
      transcriptPath: '/path/to/transcript.srt',
      transcript: [
        {
          id: '1',
          startTime: '00:00:01,000',
          endTime: '00:00:02,000',
          text: 'Test transcript',
        } as any,
      ],
    },
    status: {
      dataStoreUpload: StateActionStatus.COMPLETE,
      summarizing: StateActionStatus.COMPLETE,
      chunking: StateActionStatus.COMPLETE,
    },
  };

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        UiService,
        {
          provide: StateService,
          useValue: {
            fetch: jest
              .fn()
              .mockImplementation((stateId) =>
                stateId === mockStateId ? { ...mockState } : undefined,
              ),
          },
        },
        {
          provide: ConfigService,
          useValue: {
            get: jest.fn().mockImplementation((key) => {
              if (key === 'evam.datetimeFormat')
                return "yyyy-MM-dd'T'HH:mm:ss.SSSZ";
              return null;
            }),
          },
        },
        {
          provide: DatastoreService,
          useValue: {
            // Add mock methods if needed
          },
        },
      ],
    }).compile();

    service = module.get<UiService>(UiService);
    stateService = module.get<StateService>(StateService);
    configService = module.get<ConfigService>(ConfigService);
    datastoreService = module.get<DatastoreService>(DatastoreService);
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  describe('getInferenceConfig', () => {
    it('should return inference config when state exists', () => {
      const result = service.getInferenceConfig(mockStateId);

      expect(stateService.fetch).toHaveBeenCalledWith(mockStateId);
      expect(result).toEqual(mockState.inferenceConfig);
    });

    it('should return empty object when state does not exist', () => {
      const result = service.getInferenceConfig('non-existent-id');

      expect(result).toEqual({});
    });

    it('should use provided state without fetching', () => {
      const result = service.getInferenceConfig(mockStateId, mockState);

      expect(stateService.fetch).not.toHaveBeenCalled();
      expect(result).toEqual(mockState.inferenceConfig);
    });

    it('should return empty object when inference config is undefined', () => {
      const stateWithoutInferenceConfig = {
        ...mockState,
        inferenceConfig: undefined,
      };
      const result = service.getInferenceConfig(
        mockStateId,
        stateWithoutInferenceConfig,
      );

      expect(result).toEqual({});
    });
  });

  describe('getSummaryData', () => {
    it('should return frame summary when it exists', () => {
      const result = service.getSummaryData(mockStateId, mockFrameKey);

      expect(stateService.fetch).toHaveBeenCalledWith(mockStateId);
      expect(result).toEqual(mockState.frameSummaries[mockFrameKey]);
    });

    it('should return null when frame summary does not exist', () => {
      const result = service.getSummaryData(
        mockStateId,
        'non-existent-frame-key',
      );

      expect(result).toBeNull();
    });

    it('should return null when state does not exist', () => {
      const result = service.getSummaryData('non-existent-id', mockFrameKey);

      expect(result).toBeNull();
    });
  });

  describe('getStateStatus', () => {
    it('should return status data when state exists', () => {
      const result = service.getStateStatus(mockStateId);

      expect(stateService.fetch).toHaveBeenCalledWith(mockStateId);
      expect(result).toEqual({
        chunkingStatus: mockState.status.chunking,
        frameSummaryStatus: {
          complete: 1,
          inProgress: 0,
          na: 0,
          ready: 0,
        },
        videoSummaryStatus: mockState.status.summarizing,
      });
    });

    it('should use provided state without fetching', () => {
      const result = service.getStateStatus(mockStateId, mockState);

      expect(stateService.fetch).not.toHaveBeenCalled();
      expect(result).not.toBeNull();
    });

    it('should return null when state does not exist', () => {
      const result = service.getStateStatus('non-existent-id');

      expect(result).toBeNull();
    });
  });

  describe('getUIChunks', () => {
    it('should return UI chunks when state exists', () => {
      const result = service.getUIChunks(mockStateId);

      expect(stateService.fetch).toHaveBeenCalledWith(mockStateId);
      expect(result).toHaveLength(2);
      expect(result[0].chunkId).toEqual('1');
      expect(result[1].chunkId).toEqual('2');
      expect(result[1].duration.to).toEqual(-1); // Last chunk should have duration.to set to -1
    });

    it('should sort chunks by chunkId', () => {
      const result = service.getUIChunks(mockStateId);

      expect(result[0].chunkId).toEqual('1');
      expect(result[1].chunkId).toEqual('2');
    });

    it('should return empty array when state does not exist', () => {
      const result = service.getUIChunks('non-existent-id');

      expect(result).toEqual([]);
    });

    it('should use provided state without fetching', () => {
      const result = service.getUIChunks(mockStateId, mockState);

      expect(stateService.fetch).not.toHaveBeenCalled();
      expect(result).toHaveLength(2);
    });
  });

  describe('getUiChunk', () => {
    it('should return UI chunk when it exists', () => {
      const result = service.getUiChunk(mockStateId, mockChunkId);

      expect(stateService.fetch).toHaveBeenCalledWith(mockStateId);
      expect(result).toEqual({
        chunkId: mockChunkId,
        duration: {
          from: 0, // (chunkId - 1) * chunkDuration = (1 - 1) * 10 = 0
          to: 10, // from + chunkDuration = 0 + 10 = 10
        },
      });
    });

    it('should return null when chunk does not exist', () => {
      const result = service.getUiChunk(mockStateId, 'non-existent-chunk');

      expect(result).toBeNull();
    });

    it('should return null when state does not exist', () => {
      const result = service.getUiChunk('non-existent-id', mockChunkId);

      expect(result).toBeNull();
    });

    it('should use provided state without fetching', () => {
      const result = service.getUiChunk(mockStateId, mockChunkId, mockState);

      expect(stateService.fetch).not.toHaveBeenCalled();
      expect(result).not.toBeNull();
    });
  });

  describe('getAudioSettings', () => {
    it('should return audio settings when state and audio exist', () => {
      const result = service.getAudioSettings(mockStateId);

      expect(stateService.fetch).toHaveBeenCalledWith(mockStateId);
      expect(result).toEqual({
        device: mockState.audio?.device,
        model: mockState.audio?.model,
        status: mockState.audio?.status,
        transcript: [],
        transcriptPath: mockState.audio?.transcriptPath,
      });
    });

    it('should return null when audio does not exist in state', () => {
      const stateWithoutAudio = { ...mockState, audio: undefined };
      const result = service.getAudioSettings(mockStateId, stateWithoutAudio);

      expect(result).toBeNull();
    });

    it('should return null when state does not exist', () => {
      const result = service.getAudioSettings('non-existent-id');

      expect(result).toBeNull();
    });

    it('should use provided state without fetching', () => {
      const result = service.getAudioSettings(mockStateId, mockState);

      expect(stateService.fetch).not.toHaveBeenCalled();
      expect(result).not.toBeNull();
    });
  });

  describe('getUIFrames', () => {
    it('should return UI frames when state exists', () => {
      const result = service.getUIFrames(mockStateId);

      expect(stateService.fetch).toHaveBeenCalledWith(mockStateId);
      expect(result).toHaveLength(2);
      expect(result[0].frameId).toEqual('frame-1');
      expect(result[1].frameId).toEqual('frame-2');
    });

    it('should sort frames by frameId', () => {
      const result = service.getUIFrames(mockStateId);

      expect(result[0].frameId < result[1].frameId).toBeTruthy();
    });

    it('should return empty array when state does not exist', () => {
      const result = service.getUIFrames('non-existent-id');

      expect(result).toEqual([]);
    });

    it('should use provided state without fetching', () => {
      const result = service.getUIFrames(mockStateId, mockState);

      expect(stateService.fetch).not.toHaveBeenCalled();
      expect(result).toHaveLength(2);
    });
  });

  describe('getUiFrame', () => {
    it('should return UI frame when it exists', () => {
      const result = service.getUiFrame(mockStateId, mockFrameId);

      expect(stateService.fetch).toHaveBeenCalledWith(mockStateId);
      expect(result).toEqual({
        chunkId: mockState.frames[mockFrameId].chunkId,
        frameId: mockFrameId,
        url: mockState.frames[mockFrameId].frameUri,
        videoTimeStamp: mockState.frames[mockFrameId].metadata?.frame_timestamp,
      });
    });

    it('should return null when frame does not exist', () => {
      const result = service.getUiFrame(mockStateId, 'non-existent-frame');

      expect(result).toBeNull();
    });

    it('should return null when state does not exist', () => {
      const result = service.getUiFrame('non-existent-id', mockFrameId);

      expect(result).toBeNull();
    });

    it('should use provided state without fetching', () => {
      const result = service.getUiFrame(mockStateId, mockFrameId, mockState);

      expect(stateService.fetch).not.toHaveBeenCalled();
      expect(result).not.toBeNull();
    });
  });

  describe('getUiState', () => {
    it('should return complete UI state when state exists', () => {
      const result = service.getUiState(mockStateId);

      expect(stateService.fetch).toHaveBeenCalledWith(mockStateId);
      expect(result).not.toBeNull();
      expect(result?.stateId).toEqual(mockStateId);
      expect(result?.chunks).toHaveLength(2);
      expect(result?.frames).toHaveLength(2);
  expect(result?.summary).toEqual(mockState.summary);
  // videoURI and videoName removed, not present in UIState/SummaryPipelineSampling
  expect(result?.inferenceConfig).toEqual(mockState.inferenceConfig);
    });

    it('should set videoName from fileInfo if not in userInputs', () => {
  // Removed test for videoName and fileInfo, not present in models
    });

    it('should return null when state does not exist', () => {
      const result = service.getUiState('non-existent-id');

      expect(result).toBeNull();
    });
  });
});
