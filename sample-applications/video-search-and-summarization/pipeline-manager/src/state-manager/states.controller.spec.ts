// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Test, TestingModule } from '@nestjs/testing';
import { StatesController } from './states.controller';
import { StateService } from './services/state.service';
import { UiService } from './services/ui.service';
import { State, StateActionStatus } from './models/state.model';
import { UIState } from './models/uiState.model';
import { EVAMPipelines } from 'src/evam/models/evam.model';

describe('StatesController', () => {
  let controller: StatesController;
  let stateService: StateService;
  let uiService: UiService;

  // Mock state and UI state data for testing
  const mockState: Partial<State> = {
    stateId: 'test-state-id',
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  // fileInfo removed, not present in State
    userInputs: {
      chunkDuration: 10,
      samplingFrame: 10,
      frameOverlap: 2,
      multiFrame: 1,
    },
    chunks: {},
    frames: {},
    frameSummaries: {},
    systemConfig: {
      multiFrame: 5,
      frameOverlap: 2,
      evamPipeline: EVAMPipelines.BASIC_INGESTION,
      framePrompt: 'Describe this frame',
      summaryMapPrompt: 'Map prompt',
      summaryReducePrompt: 'Reduce prompt',
      summarySinglePrompt: 'Single prompt',
    },
    status: {
      dataStoreUpload: StateActionStatus.COMPLETE,
      summarizing: StateActionStatus.IN_PROGRESS,
      chunking: StateActionStatus.COMPLETE,
    },
  };

  const mockUiState: Partial<UIState> = {
    stateId: 'test-state-id',
    chunks: [],
    frames: [],
    frameSummaries: [],
    systemConfig: {
      multiFrame: 5,
      frameOverlap: 2,
      evamPipeline: EVAMPipelines.BASIC_INGESTION,
      framePrompt: 'Describe this frame',
      summaryMapPrompt: 'Map prompt',
      summaryReducePrompt: 'Reduce prompt',
      summarySinglePrompt: 'Single prompt',
    },
    userInputs: {
      chunkDuration: 10,
      samplingFrame: 10,
      frameOverlap: 2,
      multiFrame: 1,
    },
    summary: 'Test summary',
    videoSummaryStatus: StateActionStatus.IN_PROGRESS,
    frameSummaryStatus: {
      [StateActionStatus.NA]: 0,
      [StateActionStatus.READY]: 0,
      [StateActionStatus.IN_PROGRESS]: 1,
      [StateActionStatus.COMPLETE]: 0,
    },
    chunkingStatus: StateActionStatus.COMPLETE,
  };

  beforeEach(async () => {
    // Create mock services
    const mockStateService = {
      fetch: jest.fn().mockImplementation((stateId: string) => {
        if (stateId === 'test-state-id') {
          return mockState;
        }
        return undefined;
      }),
    };

    const mockUiService = {
      getUiState: jest.fn().mockImplementation((stateId: string) => {
        if (stateId === 'test-state-id') {
          return mockUiState;
        }
        return undefined;
      }),
    };

    const module: TestingModule = await Test.createTestingModule({
      controllers: [StatesController],
      providers: [
        { provide: StateService, useValue: mockStateService },
        { provide: UiService, useValue: mockUiService },
      ],
    }).compile();

    controller = module.get<StatesController>(StatesController);
    stateService = module.get<StateService>(StateService);
    uiService = module.get<UiService>(UiService);
  });

  it('should be defined', () => {
    expect(controller).toBeDefined();
  });

  describe('getStateRaw', () => {
    it('should return raw state for valid stateId', () => {
      const params = { stateId: 'test-state-id' };
      const result = controller.getStateRaw(params);
      
      expect(stateService.fetch).toHaveBeenCalledWith('test-state-id');
      expect(result).toEqual(mockState);
    });

    it('should return undefined for invalid stateId', () => {
      const params = { stateId: 'non-existent-id' };
      const result = controller.getStateRaw(params);
      
      expect(stateService.fetch).toHaveBeenCalledWith('non-existent-id');
      expect(result).toBeUndefined();
    });
  });

  describe('getState', () => {
    it('should return UI state for valid stateId', () => {
      const params = { stateId: 'test-state-id' };
      const result = controller.getState(params);
      
      expect(uiService.getUiState).toHaveBeenCalledWith('test-state-id');
      expect(result).toEqual(mockUiState);
    });

    it('should return undefined for invalid stateId', () => {
      const params = { stateId: 'non-existent-id' };
      const result = controller.getState(params);
      
      expect(uiService.getUiState).toHaveBeenCalledWith('non-existent-id');
      expect(result).toBeUndefined();
    });

    it('should log the stateId to console', () => {
      const consoleSpy = jest.spyOn(console, 'log');
      const params = { stateId: 'test-state-id' };
      
      controller.getState(params);
      
      expect(consoleSpy).toHaveBeenCalledWith('STATE', 'test-state-id');
      consoleSpy.mockRestore();
    });
  });
});
