// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Test, TestingModule } from '@nestjs/testing';
import { AudioService } from './audio.service';
import { HttpService } from '@nestjs/axios';
import { ConfigService } from '@nestjs/config';
import { DatastoreService } from 'src/datastore/services/datastore.service';
import { of } from 'rxjs';
import * as srtParserLib from 'srt-parser-2';
import { readFileSync, unlinkSync } from 'fs';

jest.mock('fs');

describe('AudioService', () => {
  let service: AudioService;
  let httpService: HttpService;
  let configService: ConfigService;
  let datastoreService: DatastoreService;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        AudioService,
        {
          provide: HttpService,
          useValue: {
            get: jest.fn(),
            post: jest.fn(),
          },
        },
        {
          provide: ConfigService,
          useValue: {
            get: jest.fn((key: string) => {
              const config = {
                'audio.host': 'http://audio-service',
                'audio.version': 'v1',
                'audio.apiModels': 'models',
                'audio.apiTranscription': 'transcription',
              };
              return config[key];
            }),
          },
        },
        {
          provide: DatastoreService,
          useValue: {
            getFile: jest.fn(),
          },
        },
      ],
    }).compile();

    service = module.get<AudioService>(AudioService);
    httpService = module.get<HttpService>(HttpService);
    configService = module.get<ConfigService>(ConfigService);
    datastoreService = module.get<DatastoreService>(DatastoreService);
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  describe('fetchModels', () => {
    it('should fetch audio models', () => {
      const mockResponse: any = { data: { models: ['model1', 'model2'] } };
      jest.spyOn(httpService, 'get').mockReturnValue(of(mockResponse));

      const result = service.fetchModels();

      expect(httpService.get).toHaveBeenCalledWith(
        'http://audio-service/v1/models',
      );
      result.subscribe((response) => {
        expect(response).toEqual(mockResponse);
      });
    });
  });

  describe('generateTranscript', () => {
    it('should generate a transcript', () => {
      const mockRequestData: any = { audioFile: 'file.mp3' };
      const mockResponse: any = { data: { transcript: 'test transcript' } };
      jest.spyOn(httpService, 'post').mockReturnValue(of(mockResponse));

      const result = service.generateTranscript(mockRequestData);

      expect(httpService.post).toHaveBeenCalledWith(
        'http://audio-service/v1/transcription',
        mockRequestData,
        {
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        },
      );
      result.subscribe((response) => {
        expect(response).toEqual(mockResponse);
      });
    });
  });

  describe('parseTranscript', () => {
    it('should parse an SRT file and return parsed content', async () => {
      const mockFilePath = '/tmp/test.srt';
      const mockFileContent = `
1
00:00:01,000 --> 00:00:02,000
Hello World
      `;
      const mockParsedSrt: any = [
        {
          id: '1',
          startTime: '00:00:01,000',
          endTime: '00:00:02,000',
          text: 'Hello World',
        },
      ];

      jest.spyOn(datastoreService, 'getFile').mockResolvedValue(mockFilePath);
      jest
        .spyOn(readFileSync as jest.Mock, 'call')
        .mockReturnValue(mockFileContent);
      jest.spyOn(unlinkSync as jest.Mock, 'call').mockImplementation();
      jest
        .spyOn(srtParserLib.default.prototype, 'fromSrt')
        .mockReturnValue(mockParsedSrt);

      const result = await service.parseTranscript('minio/path/to/file.srt');

      expect(datastoreService.getFile).toHaveBeenCalledWith(
        'minio/path/to/file.srt',
      );
      expect(readFileSync).toHaveBeenCalledWith(mockFilePath, 'utf-8');
      expect(unlinkSync).toHaveBeenCalledWith(mockFilePath);
      expect(result).toEqual(mockParsedSrt);
    });

    it('should throw an error if file is not found', async () => {
      jest.spyOn(datastoreService, 'getFile').mockResolvedValue('');

      await expect(
        service.parseTranscript('minio/path/to/file.srt'),
      ).rejects.toThrow('File not found');
    });
  });
});
