// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Test, TestingModule } from '@nestjs/testing';
import { AudioQueueService } from './audio-queue.service';
import { StateService } from '../services/state.service';
import { AudioService } from 'src/audio/services/audio.service';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { ConfigService } from '@nestjs/config';
import { PipelineEvents } from 'src/events/Pipeline.events';
import { of, throwError } from 'rxjs';
import { AudioDevice, AudioTranscriptDTO } from 'src/audio/models/audio.model';

describe('AudioQueueService', () => {
  let service: AudioQueueService;
  let stateService: jest.Mocked<StateService>;
  let audioService: jest.Mocked<AudioService>;
  let eventEmitter: jest.Mocked<EventEmitter2>;
  let configService: jest.Mocked<ConfigService>;

  const mockState: any = {
    stateId: 'test-state-id',
    fileInfo: {
      originalname: 'test-video.mp4',
    },
    systemConfig: {
      audioModel: 'whisper-large-v3',
    },
    video: {
      dataStore: {
        objectName: 'test-state-id',
        fileName: 'test-video.mp4',
      },
      videoId: 'test-state-id',
    },
  };

  const mockTranscripts: any[] = [
    {
      id: '1',
      startTime: '00:00:01,000',
      endTime: '00:00:02,000',
      text: 'Hello',
    },
    {
      id: '2',
      startTime: '00:00:03,000',
      endTime: '00:00:04,000',
      text: 'World',
    },
  ];

  beforeEach(async () => {
    const stateServiceMock = {
      fetch: jest.fn(),
      audioTrigger: jest.fn(),
      audioComplete: jest.fn(),
    };

    const audioServiceMock = {
      generateTranscript: jest.fn(),
      parseTranscript: jest.fn(),
    };

    const eventEmitterMock = {
      emit: jest.fn(),
    };

    const configServiceMock = {
      get: jest.fn(),
    };

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        AudioQueueService,
        { provide: StateService, useValue: stateServiceMock },
        { provide: AudioService, useValue: audioServiceMock },
        { provide: EventEmitter2, useValue: eventEmitterMock },
        { provide: ConfigService, useValue: configServiceMock },
      ],
    }).compile();

    service = module.get<AudioQueueService>(AudioQueueService);
    stateService = module.get(StateService) as jest.Mocked<StateService>;
    audioService = module.get(AudioService) as jest.Mocked<AudioService>;
    eventEmitter = module.get(EventEmitter2) as jest.Mocked<EventEmitter2>;
    configService = module.get(ConfigService) as jest.Mocked<ConfigService>;
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  describe('startAudioProcessing', () => {
    beforeEach(() => {
      configService.get.mockImplementation((key) => {
        if (key === 'audio.device') return 'cpu';
        if (key === 'datastore.bucketName') return 'test-bucket';
        return null;
      });
    });

    it('should add stateId to audioProcessing set', () => {
      const stateId = 'test-state-id';
      stateService.fetch.mockReturnValue(undefined);

      service.startAudioProcessing(stateId);

      expect(service.audioProcessing.has(stateId)).toBeTruthy();
    });

    it('should not process audio if state is not found', () => {
      const stateId = 'non-existent-state-id';
      stateService.fetch.mockReturnValue(undefined);

      service.startAudioProcessing(stateId);

      expect(audioService.generateTranscript).not.toHaveBeenCalled();
      expect(stateService.audioTrigger).not.toHaveBeenCalled();
    });

    it('should not process audio if audioModel is not configured', () => {
      const stateId = 'test-state-id';
      stateService.fetch.mockReturnValue({
        ...mockState,
        systemConfig: {} as any,
      } as any);

      service.startAudioProcessing(stateId);

      expect(audioService.generateTranscript).not.toHaveBeenCalled();
      expect(stateService.audioTrigger).not.toHaveBeenCalled();
    });

    it('should start audio processing with correct parameters', () => {
      const stateId = 'test-state-id';
      stateService.fetch.mockReturnValue(mockState);
      audioService.generateTranscript.mockReturnValue(
        of({
          status: 200,
          data: { transcript_path: 'test/transcript.srt' },
        } as any),
      );

      const expectedTranscriptDTO: AudioTranscriptDTO = {
        device: AudioDevice.CPU,
        include_timestamps: true,
        minio_bucket: 'test-bucket',
        model_name: 'whisper-large-v3',
        video_id: stateId,
        video_name: 'test-video.mp4',
      };

      service.startAudioProcessing(stateId);

      expect(stateService.audioTrigger).toHaveBeenCalledWith(
        stateId,
        expectedTranscriptDTO,
      );
      expect(audioService.generateTranscript).toHaveBeenCalledWith(
        expectedTranscriptDTO,
      );
    });

    it('should emit audio complete event on successful processing', () => {
      const stateId = 'test-state-id';
      stateService.fetch.mockReturnValue(mockState);
      audioService.generateTranscript.mockReturnValue(
        of({
          status: 200,
          data: { transcript_path: 'test/transcript.srt' },
        } as any),
      );

      service.startAudioProcessing(stateId);

      expect(eventEmitter.emit).toHaveBeenCalledWith(
        PipelineEvents.AUDIO_COMPLETE,
        {
          stateId,
          transcriptPath: 'test/transcript.srt',
        },
      );
      expect(eventEmitter.emit).toHaveBeenCalledWith(
        PipelineEvents.CHUNKING_STATUS,
        [stateId],
      );
      expect(service.audioProcessing.has(stateId)).toBeFalsy();
    });

    it('should emit audio error event on failed processing', () => {
      const stateId = 'test-state-id';
      stateService.fetch.mockReturnValue(mockState);
      audioService.generateTranscript.mockReturnValue(
        throwError(() => ({
          data: 'Audio processing error',
        })),
      );

      service.startAudioProcessing(stateId);

      expect(eventEmitter.emit).toHaveBeenCalledWith(
        PipelineEvents.AUDIO_ERROR,
        stateId,
      );
      expect(service.audioProcessing.has(stateId)).toBeFalsy();
    });
  });

  describe('audioComplete', () => {
    it('should do nothing if state is not found', async () => {
      const stateId = 'non-existent-state-id';
      stateService.fetch.mockReturnValue(undefined);

      await service.audioComplete({
        stateId,
        transcriptPath: 'test/transcript.srt',
      });

      expect(audioService.parseTranscript).not.toHaveBeenCalled();
      expect(stateService.audioComplete).not.toHaveBeenCalled();
    });

    it('should parse transcript and update state on completion', async () => {
      const stateId = 'test-state-id';
      const transcriptPath = 'test/transcript.srt';
      const fileName = 'transcript.srt';
      const minioPath = `${stateId}/${fileName}`;

      stateService.fetch.mockReturnValue(mockState);
      audioService.parseTranscript.mockResolvedValue(mockTranscripts);

      await service.audioComplete({ stateId, transcriptPath });

      expect(audioService.parseTranscript).toHaveBeenCalledWith(minioPath);
      expect(stateService.audioComplete).toHaveBeenCalledWith(stateId, {
        transcriptPath,
        transcripts: mockTranscripts,
      });
    });

    it('should handle transcript path with multiple slashes', async () => {
      const stateId = 'test-state-id';
      const transcriptPath = 'dir1/dir2/dir3/transcript.srt';
      const fileName = 'transcript.srt';
      const minioPath = `${stateId}/${fileName}`;

      stateService.fetch.mockReturnValue(mockState);
      audioService.parseTranscript.mockResolvedValue(mockTranscripts);

      await service.audioComplete({ stateId, transcriptPath });

      expect(audioService.parseTranscript).toHaveBeenCalledWith(minioPath);
    });
  });

  describe('isAudioProcessing', () => {
    it('should return true if state ID is in the processing set', () => {
      const stateId = 'test-state-id';
      service.audioProcessing.add(stateId);

      expect(service.isAudioProcessing(stateId)).toBeTruthy();
    });

    it('should return false if state ID is not in the processing set', () => {
      const stateId = 'test-state-id';
      service.audioProcessing.delete(stateId);

      expect(service.isAudioProcessing(stateId)).toBeFalsy();
    });

    it('should handle empty state ID correctly', () => {
      expect(service.isAudioProcessing('')).toBeFalsy();
    });
  });

  describe('edge cases', () => {
    it('should handle multiple concurrent audio processing requests', () => {
      const stateIds = ['state-1', 'state-2', 'state-3'];
      stateService.fetch.mockImplementation((id) => ({
        ...mockState,
        stateId: id,
      }));
      audioService.generateTranscript.mockReturnValue(
        of({
          status: 200,
          data: { transcript_path: 'test/transcript.srt' },
        } as any),
      );

      stateIds.forEach((id) => service.startAudioProcessing(id));

      // Verify all states were added to processing set
      stateIds.forEach((id) => {
        // All should be removed after processing
        expect(service.audioProcessing.has(id)).toBeFalsy();
      });

      // Verify generateTranscript was called for each state
      expect(audioService.generateTranscript).toHaveBeenCalledTimes(3);
    });

    it('should handle empty transcript path', async () => {
      const stateId = 'test-state-id';
      stateService.fetch.mockReturnValue(mockState);

      await service.audioComplete({ stateId, transcriptPath: '' });

      // Should attempt to use empty filename
      expect(audioService.parseTranscript).toHaveBeenCalledWith(`${stateId}/`);
    });
  });
});
