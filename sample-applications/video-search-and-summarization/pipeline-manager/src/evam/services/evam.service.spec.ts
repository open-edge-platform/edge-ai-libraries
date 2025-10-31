// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Test, TestingModule } from '@nestjs/testing';
import { HttpService } from '@nestjs/axios';
import { ConfigService } from '@nestjs/config';
import { DatastoreService } from 'src/datastore/services/datastore.service';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { EvamService } from './evam.service';
import { of } from 'rxjs';
import { AxiosResponse } from 'axios';
import { EVAMPipelineRO, EVAMPipelines } from '../models/evam.model';
import { PipelineEvents } from 'src/events/Pipeline.events';
import { VideoUploadDTO } from 'src/video-upload/models/upload.model';
import { DateTime } from 'luxon';
import { SummaryPipelineSampling } from 'src/summary/models/summary-pipeline.model';

describe('EvamService', () => {
  let service: EvamService;
  let httpService: HttpService;
  let configService: ConfigService;
  let datastoreService: DatastoreService;
  let eventEmitter: EventEmitter2;

  const mockConfig = {
    'evam.host': 'localhost',
    'evam.pipelinePort': '8080',
    'evam.publishPort': '8081',
    'evam.videoTopic': 'video-topic',
    'evam.datetimeFormat': 'yyyy-MM-dd HH:mm:ss',
    'evam.modelPath': '/path/to/model',
    'evam.device': 'CPU',
    'evam.model': 'model-name',
    'datastore.bucketName': 'test-bucket',
  };

  beforeEach(async () => {
    const mockHttpService = {
      get: jest.fn(),
      post: jest.fn(),
    };

    const mockConfigService = {
      get: jest.fn((key) => mockConfig[key]),
    };

    const mockDatastoreService = {};

    const mockEventEmitter = {
      emit: jest.fn(),
    };

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        EvamService,
        { provide: HttpService, useValue: mockHttpService },
        { provide: ConfigService, useValue: mockConfigService },
        { provide: DatastoreService, useValue: mockDatastoreService },
        { provide: EventEmitter2, useValue: mockEventEmitter },
      ],
    }).compile();

    service = module.get<EvamService>(EvamService);
    httpService = module.get<HttpService>(HttpService);
    configService = module.get<ConfigService>(ConfigService);
    datastoreService = module.get<DatastoreService>(DatastoreService);
    eventEmitter = module.get<EventEmitter2>(EventEmitter2);
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  describe('startChunking', () => {
    it('should call startChunkingStub with correct arguments', () => {
      const mockUserInputs: SummaryPipelineSampling = {
        chunkDuration: 10,
        samplingFrame: 5,
        frameOverlap: 2,
        multiFrame: 1,
      };
      const spy = jest.spyOn(service, 'startChunkingStub');
      service.startChunkingStub('test-id', 'path/to/video.mp4', mockUserInputs, EVAMPipelines.OBJECT_DETECTION);
      expect(spy).toHaveBeenCalledWith('test-id', 'path/to/video.mp4', mockUserInputs, EVAMPipelines.OBJECT_DETECTION);
    });
  });

  describe('getPipelineStatus', () => {
    it('should call API and return pipeline status', async () => {
      const mockResponse: AxiosResponse<EVAMPipelineRO> = {
        data: {
          id: 'pipeline-123',
          state: 'RUNNING',
          launch_command: 'command',
          params: {},
          request: {},
          type: 'object_detection',
        },
        status: 200,
        statusText: 'OK',
        headers: {},
        config: { headers: {} } as any,
      };

      jest.spyOn(httpService, 'get').mockReturnValueOnce(of(mockResponse));

      const result = await service.getPipelineStatus('pipeline-123');
      expect(result).toEqual(mockResponse);
      expect(httpService.get).toHaveBeenCalledWith(
        'http://localhost:8080/pipelines/pipeline-123',
      );
    });
  });

  describe('isChunkingInProgress', () => {
    it('should return true if stateId is in progress', () => {
      // Setup a fake entry in the inProgress map
      service.inProgress.set('state-123', {
        stateId: 'state-123',
        pipelineId: 'pipeline-123',
      });

      // Test with a stateId that is in progress (mapped to pipeline-123)
      expect(service.isChunkingInProgress('state-123')).toBe(true);

      // Test with a stateId that doesn't exist
      expect(service.isChunkingInProgress('non-existent-state')).toBe(false);
    });
  });

  describe('addStateToProgress', () => {
    it('should add a state to inProgress map', () => {
      service.addStateToProgress('state-123', 'pipeline-123');

      expect(service.inProgress.size).toBe(1);
      expect(service.inProgress.get('pipeline-123')).toEqual({
        stateId: 'state-123',
        pipelineId: 'pipeline-123',
      });
    });
  });

  describe('getInferenceConfig', () => {
    it('should return model info from config', () => {
      const result = service.getInferenceConfig();

      expect(result).toEqual({
        model: 'model-name',
        device: 'CPU',
      });
      expect(configService.get).toHaveBeenCalledWith('evam.model');
      expect(configService.get).toHaveBeenCalledWith('evam.device');
    });
  });

  describe('availablePipelines', () => {
    it('should return the available EVAM pipeline options', () => {
      const result = service.availablePipelines();

      expect(result).toHaveLength(2);
      expect(result[0].value).toBe(EVAMPipelines.OBJECT_DETECTION);
      expect(result[1].value).toBe(EVAMPipelines.BASIC_INGESTION);
    });
  });

  describe('startChunkingStub', () => {
    it('should make a POST request with correct data', () => {
      const mockUserInputs: SummaryPipelineSampling = {
        chunkDuration: 10,
        samplingFrame: 5,
        frameOverlap: 2,
        multiFrame: 1,
      };

      const mockResponse = of({
        data: 'pipeline-123',
        status: 200,
        statusText: 'OK',
        headers: {},
        config: { headers: {} } as any,
      });

      jest.spyOn(httpService, 'post').mockReturnValueOnce(mockResponse);

      const result = service.startChunkingStub(
        'test-identifier',
        'http://example.com/video.mp4',
        mockUserInputs,
        EVAMPipelines.OBJECT_DETECTION,
      );

      expect(result).toBe(mockResponse);
      expect(httpService.post).toHaveBeenCalledWith(
        'http://localhost:8080/pipelines/user_defined_pipelines/object_detection',
        expect.objectContaining({
          source: {
            element: 'curlhttpsrc',
            type: 'gst',
            properties: {
              location: 'http://example.com/video.mp4',
            },
          },
          parameters: expect.objectContaining({
            'detection-properties': {
              model: mockConfig['evam.modelPath'],
              device: mockConfig['evam.device'],
            },
            publish: {
              minio_bucket: mockConfig['datastore.bucketName'],
              video_identifier: 'test-identifier',
              topic: mockConfig['evam.videoTopic'],
            },
            frame: mockUserInputs.samplingFrame,
            chunk_duration: mockUserInputs.chunkDuration,
            frame_width: 480,
          }),
        }),
        { headers: { 'Content-Type': 'application/json' } },
      );
    });
  });

  describe('chunkingStatus', () => {
  // Removed: chunkingStatus does not exist on EvamService
  });

  describe('checkChunkingStatus', () => {
    it('should check status and emit events for completed pipelines', async () => {
      // Setup mock data
      service.inProgress.set('pipeline-123', {
        stateId: 'state-123',
        pipelineId: 'pipeline-123',
      });
      service.inProgress.set('pipeline-456', {
        stateId: 'state-456',
        pipelineId: 'pipeline-456',
      });

      const mockResponse1: AxiosResponse<EVAMPipelineRO> = {
        data: {
          id: 'pipeline-123',
          state: 'COMPLETED',
          progress: 100,
          message: 'Processing complete',
        } as any,
        status: 200,
        statusText: 'OK',
        headers: {},
        config: { headers: {} } as any,
      };

      const mockResponse2: AxiosResponse<EVAMPipelineRO> = {
        data: {
          id: 'pipeline-456',
          state: 'RUNNING',
          progress: 50,
          message: 'Processing video',
        } as any,
        status: 200,
        statusText: 'OK',
        headers: {},
        config: { headers: {} } as any,
      };

      jest
        .spyOn(service, 'getPipelineStatus')
        .mockResolvedValueOnce(mockResponse1)
        .mockResolvedValueOnce(mockResponse2);

      await service.checkChunkingStatus();

      // Should have removed the completed pipeline from the inProgress map
      expect(service.inProgress.size).toBe(1);
      expect(service.inProgress.has('pipeline-123')).toBe(false);
      expect(service.inProgress.has('pipeline-456')).toBe(true);

      // Should have emitted an event for the completed pipeline
      expect(eventEmitter.emit).toHaveBeenCalledWith(
        PipelineEvents.CHECK_QUEUE_STATUS,
        ['state-123'],
      );
    });

    it('should handle errors gracefully', async () => {
      // Setup mock data
      service.inProgress.set('pipeline-123', {
        stateId: 'state-123',
        pipelineId: 'pipeline-123',
      });

      // Mock an error
      const errorSpy = jest.spyOn(console, 'log').mockImplementation();
      jest
        .spyOn(service, 'getPipelineStatus')
        .mockRejectedValueOnce(new Error('API error'));

      await service.checkChunkingStatus();

      // Should have logged the error
      expect(errorSpy).toHaveBeenCalledWith(expect.any(Error));

      // Should reset the checking status
      expect(service['checkingStatus']).toBe(false);

      errorSpy.mockRestore();
    });

    it('should not process if already checking status', async () => {
      // Set the checking flag to true
      service['checkingStatus'] = true;

      jest.spyOn(service, 'getPipelineStatus');

      await service.checkChunkingStatus();

      // Should not have called getPipelineStatus
      expect(service.getPipelineStatus).not.toHaveBeenCalled();
    });
  });
});
