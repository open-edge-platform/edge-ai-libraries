// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Test, TestingModule } from '@nestjs/testing';
import { SummaryQueueService } from './summary-queue.service';
import { StateService } from '../services/state.service';
import { LlmService } from 'src/language-model/services/llm.service';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { ConfigService } from '@nestjs/config';
import { PipelineEvents, SummaryCompleteRO } from 'src/events/Pipeline.events';
import { Subject } from 'rxjs';
import { TemplateService } from 'src/language-model/services/template.service';
import { InferenceCountService } from 'src/language-model/services/inference-count.service';

describe('SummaryQueueService', () => {
  let service: SummaryQueueService;
  let stateService: jest.Mocked<StateService>;
  let llmService: jest.Mocked<LlmService>;
  let eventEmitter: jest.Mocked<EventEmitter2>;
  let configService: jest.Mocked<ConfigService>;
  let templateService: jest.Mocked<TemplateService>;

  const mockStateId = 'test-state-id';

  const mockState = {
    stateId: mockStateId,
    frameSummaries: {
      'frame-1': { startFrame: '1', summary: 'First frame summary' },
      'frame-2': { startFrame: '2', summary: 'Second frame summary' },
      'frame-3': { startFrame: '3', summary: 'Third frame summary' },
    },
    systemConfig: {
      summaryMapPrompt: 'Map prompt',
      summaryReducePrompt: 'Reduce prompt',
      summarySinglePrompt: 'Single prompt',
    },
    audio: {
      transcript: [
        {
          id: '1',
          startTime: '00:00:01,000',
          endTime: '00:00:02,000',
          text: 'Test audio transcript',
        },
      ],
    },
  };

  beforeEach(async () => {
    // Create mocks for all dependencies
    const stateServiceMock = {
      fetch: jest.fn(),
      addTextInferenceConfig: jest.fn(),
    };

    const llmServiceMock = {
      summarizeMapReduce: jest.fn().mockReturnValue(Promise.resolve()),
      getInferenceConfig: jest.fn().mockReturnValue({ model: 'test-model' }),
    };

    const eventEmitterMock = {
      emit: jest.fn(),
    };

    const configServiceMock = {
      get: jest.fn((key) => {
        if (key === 'openai.llmSummarization.concurrent') return 2;
        if (key === 'openai.usecase') return 'default';
        return null;
      }),
    };

    const templateServiceMock = {
      // Add template service methods if needed
    };

    const inferenceCountServiceMock = {
      incrementLlmProcessCount: jest.fn(),
      decrementLlmProcessCount: jest.fn(),
      hasLlmSlots: jest.fn().mockReturnValue(true),
    };

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        SummaryQueueService,
        { provide: StateService, useValue: stateServiceMock },
        { provide: LlmService, useValue: llmServiceMock },
        { provide: EventEmitter2, useValue: eventEmitterMock },
        { provide: ConfigService, useValue: configServiceMock },
  { provide: 'InferenceCountService', useValue: inferenceCountServiceMock },
  { provide: InferenceCountService, useValue: inferenceCountServiceMock },
        { provide: TemplateService, useValue: templateServiceMock },
      ],
    }).compile();

    service = module.get<SummaryQueueService>(SummaryQueueService);
    stateService = module.get(StateService) as jest.Mocked<StateService>;
    llmService = module.get(LlmService) as jest.Mocked<LlmService>;
    eventEmitter = module.get(EventEmitter2) as jest.Mocked<EventEmitter2>;
    configService = module.get(ConfigService) as jest.Mocked<ConfigService>;
    templateService = module.get(
      TemplateService,
    ) as jest.Mocked<TemplateService>;
    // Make hasLlmSlots reflect current processing queue length (capacity = 2)
    (inferenceCountServiceMock.hasLlmSlots as jest.Mock).mockImplementation(
      () => service.processing.length < 2,
    );

    // Reset arrays and properties before each test
    service.waiting = [];
    service.processing = [];
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  describe('streamTrigger', () => {
    it('should add a state ID to the waiting queue when triggered', () => {
      // Act
      service.streamTrigger({ stateId: mockStateId });

      // Assert
      expect(service.waiting).toHaveLength(1);
      expect(service.waiting[0]).toEqual({ stateId: mockStateId });
    });

    it('should handle multiple trigger events', () => {
      // Act
      service.streamTrigger({ stateId: 'state-1' });
      service.streamTrigger({ stateId: 'state-2' });
      service.streamTrigger({ stateId: 'state-3' });

      // Assert
      expect(service.waiting).toHaveLength(3);
      expect(service.waiting[0]).toEqual({ stateId: 'state-1' });
      expect(service.waiting[1]).toEqual({ stateId: 'state-2' });
      expect(service.waiting[2]).toEqual({ stateId: 'state-3' });
    });
  });

  describe('startVideoSummary', () => {
    let mockSubject: Subject<string>;

    beforeEach(() => {
      mockSubject = new Subject<string>();
      stateService.fetch.mockReturnValue(mockState as any);
    });

    it('should emit a SUMMARY_PROCESSING event', () => {
      // Act
      service.startVideoSummary({ stateId: mockStateId });

      // Assert
      expect(eventEmitter.emit).toHaveBeenCalledWith(
        PipelineEvents.SUMMARY_PROCESSING,
        { stateId: mockStateId },
      );
    });

    it('should not process if state is not found', () => {
      // Arrange
      stateService.fetch.mockReturnValue(undefined);

      // Act
      service.startVideoSummary({ stateId: mockStateId });

      // Assert
      expect(llmService.summarizeMapReduce).not.toHaveBeenCalled();
    });

    it('should not process if there are no frame summaries', () => {
      // Arrange
      stateService.fetch.mockReturnValue({
        ...mockState,
        frameSummaries: {},
      } as any);

      // Act
      service.startVideoSummary({ stateId: mockStateId });

      // Assert
      expect(llmService.summarizeMapReduce).not.toHaveBeenCalled();
    });

    it('should call summarizeMapReduce with correct parameters', () => {
      // Arrange

      let texts: string[] = [];
      let mapPrompt: string = 'MapPrompt';
      let reducePrompt: string = 'Reduce prompt';

      jest
        .spyOn(llmService, 'summarizeMapReduce')
        .mockImplementation(
          (texts, mapPrompt, reducePrompt, singlePrompt, streamer) => {
            // Simulate completion after processing
            setTimeout(() => {
              streamer.next('Summary part 1. ');
              streamer.next('Summary part 2.');
              streamer.complete();
            }, 0);
            return Promise.resolve('');
          },
        );

      // Act
      service.startVideoSummary({ stateId: mockStateId });

      // Assert
      expect(llmService.getInferenceConfig).toHaveBeenCalled();
      expect(stateService.addTextInferenceConfig).toHaveBeenCalledWith(
        mockStateId,
        expect.any(Object),
      );

      expect(llmService.summarizeMapReduce).toHaveBeenCalledWith(
        expect.any(Array), // texts
        expect.stringContaining('Map prompt'), // mapPrompt
        'Reduce prompt', // reducePrompt
        'Single prompt', // singlePrompt
        expect.any(Subject), // streamer
      );
    });

    it('should include audio transcripts in the prompt when available', () => {
      // Act
      service.startVideoSummary({ stateId: mockStateId });

      // Verify that summarizeMapReduce was called with a mapPrompt containing transcripts
      const callArgs = llmService.summarizeMapReduce.mock.calls[0];
      const mapPrompt = callArgs[1];

      expect(mapPrompt).toContain('Audio transcripts for this video:');
      expect(mapPrompt).toContain('00:00:01,000 --> 00:00:02,000');
      expect(mapPrompt).toContain('Test audio transcript');
    });

    it('should not include audio transcript section when not available', () => {
      // Arrange - state without audio
      stateService.fetch.mockReturnValue({
        ...mockState,
        audio: undefined,
      } as any);

      // Act
      service.startVideoSummary({ stateId: mockStateId });

      // Verify that summarizeMapReduce was called with a mapPrompt without transcripts
      const callArgs = llmService.summarizeMapReduce.mock.calls[0];
      const mapPrompt = callArgs[1];

      expect(mapPrompt).not.toContain('Audio transcripts for this video:');
    });

    it('should handle empty audio transcript array', () => {
      // Arrange - state with empty transcript array
      stateService.fetch.mockReturnValue({
        ...mockState,
        audio: { transcript: [] },
      } as any);

      // Act
      service.startVideoSummary({ stateId: mockStateId });

      // Verify that summarizeMapReduce was called with a mapPrompt without transcripts
      const callArgs = llmService.summarizeMapReduce.mock.calls[0];
      const mapPrompt = callArgs[1];

      expect(mapPrompt).not.toContain('Audio transcripts for this video:');
    });

    it('should handle error in summarizeMapReduce', () => {
      // Arrange
      const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation();
      llmService.summarizeMapReduce.mockRejectedValue(new Error('API error'));

      // Act
      service.startVideoSummary({ stateId: mockStateId });

      // Let the promise rejection propagate
      return new Promise(process.nextTick).then(() => {
        // Assert
        expect(consoleErrorSpy).toHaveBeenCalledWith(
          'Error summarizing video:',
          expect.any(Error),
        );
        consoleErrorSpy.mockRestore();
      });
    });

    it('should emit events when streaming summary results', (done) => {
      // Arrange
      jest
        .spyOn(llmService, 'summarizeMapReduce')
        .mockImplementation(
          (texts, mapPrompt, reducePrompt, singlePrompt, streamer) => {
            // Simulate completion after processing
            setTimeout(() => {
              streamer.next('Summary part 1. ');
              streamer.next('Summary part 2.');
              streamer.complete();
            }, 10);
            return Promise.resolve('');
          },
        );

      const expectedSummary = 'Summary part 1. Summary part 2.';

      // Setup tracking for emitted events
      let streamChunksReceived: string[] = [];
      let summaryCompleteReceived = false;

      eventEmitter.emit.mockImplementation((event, payload) => {
        if (event === PipelineEvents.SUMMARY_STREAM) {
          streamChunksReceived.push(payload.streamChunk);
        }
        if (event === PipelineEvents.SUMMARY_COMPLETE) {
          summaryCompleteReceived = true;
          expect(payload).toEqual({
            stateId: mockStateId,
            summary: expectedSummary,
          });

          // Verify all expected events were emitted
          expect(streamChunksReceived).toEqual([
            'Summary part 1. ',
            'Summary part 2.',
          ]);
          expect(summaryCompleteReceived).toBe(true);
          done();
        }
        return true;
      });

      // Act
      service.startVideoSummary({ stateId: mockStateId });
    });
  });

  describe('processQueue', () => {
    it('should not process anything when processing queue is at capacity', () => {
      // Arrange
      service.waiting = [{ stateId: 'state-1' }, { stateId: 'state-2' }];
      service.processing = [{ stateId: 'state-3' }, { stateId: 'state-4' }];
  // service.maxConcurrent = 2; // Removed: property does not exist

      const startVideoSummarySpy = jest.spyOn(service, 'startVideoSummary');

      // Act
      service.processQueue();

      // Assert
      expect(startVideoSummarySpy).not.toHaveBeenCalled();
      expect(service.waiting).toHaveLength(2);
      expect(service.processing).toHaveLength(2);
    });

    it('should process items from waiting queue when capacity is available', () => {
      // Arrange
      service.waiting = [{ stateId: 'state-1' }, { stateId: 'state-2' }];
      service.processing = [{ stateId: 'state-3' }];
  // service.maxConcurrent = 2; // Removed: property does not exist

      const startVideoSummarySpy = jest.spyOn(service, 'startVideoSummary');

      // Act
      service.processQueue();

      // Assert
      expect(startVideoSummarySpy).toHaveBeenCalledWith({ stateId: 'state-1' });
      expect(service.waiting).toHaveLength(1);
      expect(service.processing).toHaveLength(2);
    });

    it('should not take action if waiting queue is empty', () => {
      // Arrange
      service.waiting = [];
      service.processing = [{ stateId: 'state-3' }];
  // service.maxConcurrent = 2; // Removed: property does not exist

      const startVideoSummarySpy = jest.spyOn(service, 'startVideoSummary');

      // Act
      service.processQueue();

      // Assert
      expect(startVideoSummarySpy).not.toHaveBeenCalled();
      expect(service.waiting).toHaveLength(0);
      expect(service.processing).toHaveLength(1);
    });

    it('should handle multiple items in the waiting queue', () => {
      // Arrange
      service.waiting = [
        { stateId: 'state-1' },
        { stateId: 'state-2' },
        { stateId: 'state-3' },
      ];
      service.processing = [];

      const startVideoSummarySpy = jest.spyOn(service, 'startVideoSummary');

      // Act
      service.processQueue();

      // Assert
      expect(startVideoSummarySpy).toHaveBeenCalledWith({ stateId: 'state-1' });
      expect(service.waiting).toHaveLength(2);
      expect(service.processing).toHaveLength(1);
    });
  });

  describe('summaryComplete', () => {
    it('should remove the completed state from the processing queue', () => {
      // Arrange
      service.processing = [
        { stateId: 'state-1' },
        { stateId: mockStateId },
        { stateId: 'state-3' },
      ];

      const payload: SummaryCompleteRO = {
        stateId: mockStateId,
        summary: 'Test summary',
      };

      // Act
      service.summaryComplete(payload);

      // Assert
      expect(service.processing).toHaveLength(2);
      expect(
        service.processing.find((item) => item.stateId === mockStateId),
      ).toBeUndefined();
      expect(service.processing[0].stateId).toBe('state-1');
      expect(service.processing[1].stateId).toBe('state-3');
    });

    it('should handle state ID not found in processing', () => {
      // Arrange
      service.processing = [{ stateId: 'state-1' }, { stateId: 'state-2' }];

      const payload: SummaryCompleteRO = {
        stateId: 'non-existent-state',
        summary: 'Test summary',
      };

      // Act
      service.summaryComplete(payload);

      // Assert
      expect(service.processing).toHaveLength(2);
      expect(service.processing[0].stateId).toBe('state-1');
      expect(service.processing[1].stateId).toBe('state-2');
    });

    it('should handle empty processing queue', () => {
      // Arrange
      service.processing = [];

      const payload: SummaryCompleteRO = {
        stateId: mockStateId,
        summary: 'Test summary',
      };

      // Act
      service.summaryComplete(payload);

      // Assert
      expect(service.processing).toHaveLength(0);
    });
  });
});
