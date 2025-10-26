// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Test, TestingModule } from '@nestjs/testing';
import { EventsGateway } from './events.gateway';
import { UiService } from 'src/state-manager/services/ui.service';
import { Server, Socket } from 'socket.io';
import {
  SocketEvent,
  SocketFrameSummarySyncDTO,
} from 'src/events/socket.events';
import { PipelineEvents, SummaryStreamChunk } from 'src/events/Pipeline.events';
import { StateActionStatus } from 'src/state-manager/models/state.model';

describe('EventsGateway', () => {
  let gateway: EventsGateway;
  let uiService: UiService;
  let server: Server;

  // Mock Socket.io server
  const mockServer = {
    to: jest.fn().mockReturnThis(),
    emit: jest.fn(),
  };

  // Mock socket client
  const mockClient = {
    join: jest.fn(),
    emit: jest.fn(),
  } as unknown as Socket;

  // Mock data
  const mockStateId = 'test-state-123';
  const mockFrameKey = 'frame-123';

  const mockUiState: any = {
    stateId: mockStateId,
    videoURI: 'test-video-uri',
    chunks: [],
    frames: [],
    userInputs: {
      videoName: 'test-video.mp4',
      chunkDuration: 30,
    },
    frameSummaries: [],
    summary: 'Test summary',
    systemConfig: {},
    chunkingStatus: StateActionStatus.COMPLETE,
    frameSummaryStatus: {
      complete: 1,
      inProgress: 0,
      na: 0,
      ready: 0,
    },
    videoSummaryStatus: StateActionStatus.COMPLETE,
    inferenceConfig: { model: 'test-model' },
  };

  const mockStateStatus = {
    chunkingStatus: StateActionStatus.COMPLETE,
    frameSummaryStatus: {
      complete: 1,
      inProgress: 0,
      na: 0,
      ready: 0,
    },
    videoSummaryStatus: StateActionStatus.COMPLETE,
  };

  const mockChunksData = {
    chunks: [
      {
        chunkId: '1',
        duration: { from: 0, to: 30 },
      },
    ],
    frames: [
      {
        chunkId: '1',
        frameId: 'frame-1',
        url: 'frame-1.jpg',
        videoTimeStamp: 10,
      },
    ],
  };

  const mockFrameSummary: any = {
    frameId: mockFrameKey,
    summary: 'This is a test frame summary',
    status: StateActionStatus.COMPLETE,
  };

  const mockInferenceConfig: any = {
    model: 'test-model',
    temperature: 0.7,
  };

  beforeEach(async () => {
    const mockUiService = {
      getUiState: jest.fn(),
      getStateStatus: jest.fn(),
      getUIChunks: jest.fn(),
      getUIFrames: jest.fn(),
      getSummaryData: jest.fn(),
      getInferenceConfig: jest.fn(),
    };

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        EventsGateway,
        {
          provide: UiService,
          useValue: mockUiService,
        },
      ],
    }).compile();

    gateway = module.get<EventsGateway>(EventsGateway);
    uiService = module.get<UiService>(UiService);

    // Manually inject the mock server
    gateway.server = mockServer as unknown as Server;
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  it('should be defined', () => {
    expect(gateway).toBeDefined();
  });

  describe('syncState', () => {
    it('should emit UI state when state exists', () => {
      // Arrange
      jest.spyOn(uiService, 'getUiState').mockReturnValue(mockUiState);

      // Act
      gateway.syncState({ stateId: mockStateId });

      // Assert
      expect(uiService.getUiState).toHaveBeenCalledWith(mockStateId);
      expect(mockServer.to).toHaveBeenCalledWith(mockStateId);
      expect(mockServer.emit).toHaveBeenCalledWith(
        `summary:sync/${mockStateId}`,
        mockUiState,
      );
    });

    it('should not emit UI state when state does not exist', () => {
      // Arrange
      jest.spyOn(uiService, 'getUiState').mockReturnValue(null);

      // Act
      gateway.syncState({ stateId: mockStateId });

      // Assert
      expect(uiService.getUiState).toHaveBeenCalledWith(mockStateId);
      expect(mockServer.to).not.toHaveBeenCalled();
      expect(mockServer.emit).not.toHaveBeenCalled();
    });
  });

  describe('stateStatusSync', () => {
    it('should emit state status when status exists', () => {
      // Arrange
      jest.spyOn(uiService, 'getStateStatus').mockReturnValue(mockStateStatus);

      // Act
      gateway.stateStatusSync({ stateId: mockStateId });

      // Assert
      expect(uiService.getStateStatus).toHaveBeenCalledWith(mockStateId);
      expect(mockServer.to).toHaveBeenCalledWith(mockStateId);
      expect(mockServer.emit).toHaveBeenCalledWith(
        `summary:sync/${mockStateId}/status`,
        mockStateStatus,
      );
    });

    it('should not emit state status when status does not exist', () => {
      // Arrange
      jest.spyOn(uiService, 'getStateStatus').mockReturnValue(null);

      // Act
      gateway.stateStatusSync({ stateId: mockStateId });

      // Assert
      expect(uiService.getStateStatus).toHaveBeenCalledWith(mockStateId);
      expect(mockServer.to).not.toHaveBeenCalled();
      expect(mockServer.emit).not.toHaveBeenCalled();
    });
  });

  describe('syncChunkingData', () => {
    it('should emit chunks and frames data', () => {
      // Arrange
      jest
        .spyOn(uiService, 'getUIChunks')
        .mockReturnValue(mockChunksData.chunks);
      jest
        .spyOn(uiService, 'getUIFrames')
        .mockReturnValue(mockChunksData.frames);

      // Act
      gateway.syncChunkingData(mockStateId);

      // Assert
      expect(uiService.getUIChunks).toHaveBeenCalledWith(mockStateId);
      expect(uiService.getUIFrames).toHaveBeenCalledWith(mockStateId);
      expect(mockServer.to).toHaveBeenCalledWith(mockStateId);
      expect(mockServer.emit).toHaveBeenCalledWith(
        `summary:sync/${mockStateId}/chunks`,
        {
          chunks: mockChunksData.chunks,
          frames: mockChunksData.frames,
        },
      );
    });
  });

  describe('frameSummarySync', () => {
    it('should emit frame summary when it exists', () => {
      // Arrange
      const payload: SocketFrameSummarySyncDTO = {
        stateId: mockStateId,
        frameKey: mockFrameKey,
      };

      jest.spyOn(uiService, 'getSummaryData').mockReturnValue(mockFrameSummary);

      // Act
      gateway.frameSummarySync(payload);

      // Assert
      expect(uiService.getSummaryData).toHaveBeenCalledWith(
        mockStateId,
        mockFrameKey,
      );
      expect(mockServer.to).toHaveBeenCalledWith(mockStateId);
      expect(mockServer.emit).toHaveBeenCalledWith(
        `summary:sync/${mockStateId}/frameSummary`,
        {
          stateId: mockStateId,
          ...mockFrameSummary,
        },
      );
    });

    it('should not emit frame summary when it does not exist', () => {
      // Arrange
      const payload: SocketFrameSummarySyncDTO = {
        stateId: mockStateId,
        frameKey: mockFrameKey,
      };

      jest.spyOn(uiService, 'getSummaryData').mockReturnValue(null);

      // Act
      gateway.frameSummarySync(payload);

      // Assert
      expect(uiService.getSummaryData).toHaveBeenCalledWith(
        mockStateId,
        mockFrameKey,
      );
      expect(mockServer.to).not.toHaveBeenCalled();
      expect(mockServer.emit).not.toHaveBeenCalled();
    });
  });

  describe('stateConfigSync', () => {
    it('should emit inference config', () => {
      // Arrange
      jest
        .spyOn(uiService, 'getInferenceConfig')
        .mockReturnValue(mockInferenceConfig);

      // Act
      gateway.stateConfigSync(mockStateId);

      // Assert
      expect(uiService.getInferenceConfig).toHaveBeenCalledWith(mockStateId);
      expect(mockServer.to).toHaveBeenCalledWith(mockStateId);
      expect(mockServer.emit).toHaveBeenCalledWith(
        `summary:sync/${mockStateId}/inferenceConfig`,
        mockInferenceConfig,
      );
    });
  });

  describe('summarySync', () => {
    it('should emit summary data', () => {
      // Arrange
      const summaryData = {
        stateId: mockStateId,
        summary: 'This is a test summary',
      };

      // Act
      gateway.summarySync(summaryData);

      // Assert
      expect(mockServer.to).toHaveBeenCalledWith(mockStateId);
      expect(mockServer.emit).toHaveBeenCalledWith(
        `summary:sync/${mockStateId}/summary`,
        summaryData,
      );
    });
  });

  describe('summaryStream', () => {
    it('should emit summary stream chunk', () => {
      // Arrange
      const summaryStreamData: SummaryStreamChunk = {
        stateId: mockStateId,
        streamChunk: 'This is a stream chunk',
      };

      // Act
      gateway.summaryStream(summaryStreamData);

      // Assert
      expect(mockServer.to).toHaveBeenCalledWith(mockStateId);
      expect(mockServer.emit).toHaveBeenCalledWith(
        `summary:sync/${mockStateId}/summaryStream`,
        summaryStreamData.streamChunk,
      );
    });
  });

  describe('handleJoin', () => {
    it('should join client to room', () => {
      // Act
      gateway.handleJoin(mockClient, mockStateId);

      // Assert
      expect(mockClient.join).toHaveBeenCalledWith(mockStateId);
    });
  });



  describe('error handling', () => {
    it('should handle errors during state sync', () => {
      // Arrange
      jest.spyOn(uiService, 'getUiState').mockImplementation(() => {
        throw new Error('Test error');
      });

      // Act & Assert
      expect(() => gateway.syncState({ stateId: mockStateId })).toThrow(
        'Test error',
      );
    });

    it('should handle empty state ID in state sync', () => {
      // Arrange
      const emptyStateId = '';

      // Act
      gateway.syncState({ stateId: emptyStateId });

      // Assert
      expect(uiService.getUiState).toHaveBeenCalledWith(emptyStateId);
    });
  });
});
