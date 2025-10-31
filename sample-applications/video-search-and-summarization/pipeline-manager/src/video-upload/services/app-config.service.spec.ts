// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Test, TestingModule } from '@nestjs/testing';
import { AppConfigService } from './app-config.service';
import { ConfigService } from '@nestjs/config';
import { TemplateService } from 'src/language-model/services/template.service';
import { EvamService } from 'src/evam/services/evam.service';
import { AudioService } from 'src/audio/services/audio.service';
import { EVAMPipelines } from 'src/evam/models/evam.model';
import { of, throwError } from 'rxjs';
import { SystemConfig, SystemConfigWithMeta } from '../models/upload.model';

describe('AppConfigService', () => {
  let service: AppConfigService;
  let configService: ConfigService;
  let templateService: TemplateService;
  let evamService: EvamService;
  let audioService: AudioService;

  // Mock data for tests
  const mockTemplates = {
    defaultFrames: 'Default frame template',
    defaultSummary: 'Default summary template',
    defaultReduce: 'Default reduce template',
    defaultSingle: 'Default single template',
  };

  const mockEvamPipelines = [
    { id: 'pipeline1', name: 'Pipeline 1' },
    { id: 'pipeline2', name: 'Pipeline 2' },
  ];

  const mockAudioModels: any = {
    data: {
      default_model: 'whisper',
      models: [
        { id: 'whisper', name: 'Whisper' },
        { id: 'wav2vec', name: 'Wav2Vec' },
      ],
    },
  };

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        AppConfigService,
        {
          provide: ConfigService,
          useValue: {
            get: jest.fn((key: string) => {
              const config = {
                'openai.usecase': 'default',
                'openai.vlmCaptioning.frameOverlap': 3,
                'openai.vlmCaptioning.multiFrame': 12,
                'audio.host': 'http://localhost:8080',
              };
              return config[key];
            }),
          },
        },
        {
          provide: TemplateService,
          useValue: {
            getTemplate: jest.fn((templateName: string) => {
              const templates = {
                defaultFrames: mockTemplates.defaultFrames,
                defaultSummary: mockTemplates.defaultSummary,
                defaultReduce: mockTemplates.defaultReduce,
                defaultSingle: mockTemplates.defaultSingle,
              };
              return templates[templateName] || '';
            }),
          },
        },
        {
          provide: EvamService,
          useValue: {
            availablePipelines: jest.fn().mockReturnValue(mockEvamPipelines),
          },
        },
        {
          provide: AudioService,
          useValue: {
            fetchModels: jest.fn(),
          },
        },
      ],
    }).compile();

    service = module.get<AppConfigService>(AppConfigService);
    configService = module.get<ConfigService>(ConfigService);
    templateService = module.get<TemplateService>(TemplateService);
    evamService = module.get<EvamService>(EvamService);
    audioService = module.get<AudioService>(AudioService);
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  describe('systemConfig', () => {
    it('should return correct system configuration', () => {
      const result = service.systemConfig();

      // Check that configuration has all required properties
      expect(result).toHaveProperty('frameOverlap');
      expect(result).toHaveProperty('evamPipeline');
      expect(result).toHaveProperty('multiFrame');
      expect(result).toHaveProperty('framePrompt');
      expect(result).toHaveProperty('summaryMapPrompt');
      expect(result).toHaveProperty('summaryReducePrompt');
      expect(result).toHaveProperty('summarySinglePrompt');

      // Check values are correct
      expect(result.frameOverlap).toBe(3);
      expect(result.evamPipeline).toBe(EVAMPipelines.OBJECT_DETECTION);
      expect(result.multiFrame).toBe(12);
      expect(result.framePrompt).toBe(mockTemplates.defaultFrames);
      expect(result.summaryMapPrompt).toBe(mockTemplates.defaultSummary);
      expect(result.summaryReducePrompt).toBe(mockTemplates.defaultReduce);
      expect(result.summarySinglePrompt).toBe(mockTemplates.defaultSingle);
    });

    it('should call ConfigService.get with correct parameters', () => {
      service.systemConfig();

      expect(configService.get).toHaveBeenCalledWith('openai.usecase');
      expect(configService.get).toHaveBeenCalledWith(
        'openai.vlmCaptioning.frameOverlap',
      );
      expect(configService.get).toHaveBeenCalledWith(
        'openai.vlmCaptioning.multiFrame',
      );
    });

    it('should call TemplateService.getTemplate with correct use case parameters', () => {
      service.systemConfig();

      expect(templateService.getTemplate).toHaveBeenCalledWith('defaultFrames');
      expect(templateService.getTemplate).toHaveBeenCalledWith(
        'defaultSummary',
      );
      expect(templateService.getTemplate).toHaveBeenCalledWith('defaultReduce');
      expect(templateService.getTemplate).toHaveBeenCalledWith('defaultSingle');
    });

    it('should handle different use case values', () => {
      jest.spyOn(configService, 'get').mockImplementation((key: string) => {
        if (key === 'openai.usecase') return 'custom';
        return 1; // Default value for other configs
      });

      service.systemConfig();

      expect(templateService.getTemplate).toHaveBeenCalledWith('customFrames');
      expect(templateService.getTemplate).toHaveBeenCalledWith('customSummary');
      expect(templateService.getTemplate).toHaveBeenCalledWith('customReduce');
      expect(templateService.getTemplate).toHaveBeenCalledWith('customSingle');
    });
  });

  describe('systemConfigWithMeta', () => {
    beforeEach(() => {
      jest.spyOn(service, 'systemConfig').mockReturnValue({
        frameOverlap: 3,
        evamPipeline: EVAMPipelines.OBJECT_DETECTION,
        multiFrame: 12,
        framePrompt: mockTemplates.defaultFrames,
        summaryMapPrompt: mockTemplates.defaultSummary,
        summaryReducePrompt: mockTemplates.defaultReduce,
        summarySinglePrompt: mockTemplates.defaultSingle,
      });
    });

    it('should include system config and evam pipelines in the result', async () => {
      jest
        .spyOn(audioService, 'fetchModels')
        .mockReturnValue(of(mockAudioModels));

      const result = await service.systemConfigWithMeta();

      expect(result).toHaveProperty('frameOverlap', 3);
      expect(result).toHaveProperty(
        'evamPipeline',
        EVAMPipelines.OBJECT_DETECTION,
      );
      expect(result).toHaveProperty('multiFrame', 12);
      expect(result).toHaveProperty('meta');
      expect(result.meta).toHaveProperty('evamPipelines', mockEvamPipelines);
    });

    it('should include audio models when audio service is available', async () => {
      jest
        .spyOn(audioService, 'fetchModels')
        .mockReturnValue(of(mockAudioModels));

      const result = await service.systemConfigWithMeta();

      expect(result.meta).toHaveProperty('defaultAudioModel', 'whisper');
      expect(result.meta).toHaveProperty('audioModels');
      expect(result.meta.audioModels).toEqual(mockAudioModels.data.models);
    });

    it('should handle errors from audio service gracefully', async () => {
      jest
        .spyOn(audioService, 'fetchModels')
        .mockReturnValue(
          throwError(() => new Error('Audio service unavailable')),
        );

      // Mock console.log to avoid polluting test output
      const consoleLogSpy = jest.spyOn(console, 'log').mockImplementation();

      const result = await service.systemConfigWithMeta();

      expect(result.meta).toHaveProperty('audioModels', []);
      expect(result.meta).not.toHaveProperty('defaultAudioModel');

      // Verify error was logged
      expect(consoleLogSpy).toHaveBeenCalledWith('Audio not available');
      expect(consoleLogSpy).toHaveBeenCalledWith(
        'Audio Error',
        expect.any(Error),
      );

      consoleLogSpy.mockRestore();
    });

    it('should call dependent services with correct parameters', async () => {
      jest
        .spyOn(audioService, 'fetchModels')
        .mockReturnValue(of(mockAudioModels));

      await service.systemConfigWithMeta();

      expect(service.systemConfig).toHaveBeenCalled();
      expect(evamService.availablePipelines).toHaveBeenCalled();
      expect(audioService.fetchModels).toHaveBeenCalled();
    });

    it('should return SystemConfigWithMeta type with all required properties', async () => {
      jest
        .spyOn(audioService, 'fetchModels')
        .mockReturnValue(of(mockAudioModels));

      const result: SystemConfigWithMeta = await service.systemConfigWithMeta();

      // Verify the return type has all required properties
      const requiredProperties: (keyof SystemConfigWithMeta)[] = [
        'frameOverlap',
        'evamPipeline',
        'multiFrame',
        'framePrompt',
        'summaryMapPrompt',
        'summaryReducePrompt',
        'summarySinglePrompt',
        'meta',
      ];

      for (const prop of requiredProperties) {
        expect(result).toHaveProperty(prop);
      }

      // Verify meta object has all required properties
      expect(result.meta).toHaveProperty('evamPipelines');
      expect(result.meta).toHaveProperty('audioModels');
    });
  });
});
