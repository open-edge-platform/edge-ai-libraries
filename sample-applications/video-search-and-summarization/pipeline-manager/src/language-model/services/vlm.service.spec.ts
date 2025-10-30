// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Test, TestingModule } from '@nestjs/testing';
import { VlmService } from './vlm.service';
import { DatastoreService } from 'src/datastore/services/datastore.service';
import { ConfigService } from '@nestjs/config';
import { TemplateService } from './template.service';
import { HttpsProxyAgent } from 'https-proxy-agent';
import { OpenAI } from 'openai';
import { of } from 'rxjs';
import { OpenaiHelperService } from './openai-helper.service';
import { FeaturesService } from 'src/features/features.service';
import { InferenceCountService } from './inference-count.service';

// Mock OpenAI Client
jest.mock('openai', () => {
  return {
    OpenAI: jest.fn().mockImplementation(() => ({
      chat: {
        completions: {
          create: jest.fn().mockResolvedValue({
            choices: [{ message: { content: 'Mocked response content' } }],
          }),
        },
      },
      models: {
        list: jest.fn().mockResolvedValue({
          data: [{ id: 'gpt-4-vision-preview' }],
        }),
      },
    })),
  };
});

// Mock HttpsProxyAgent
jest.mock('https-proxy-agent', () => ({
  HttpsProxyAgent: jest.fn().mockImplementation(() => ({})),
}));

describe('VlmService', () => {
  let service: VlmService;
  let datastoreService: DatastoreService;
  let configService: ConfigService;
  let templateService: TemplateService;

  // Mock config values
  const mockConfigValues = {
    'openai.vlmCaptioning.apiKey': 'test-api-key',
    'openai.vlmCaptioning.apiBase': 'https://api.openai.com/v1',
    'openai.vlmCaptioning.device': 'CPU',
    'proxy.noProxy': '',
    'proxy.url': 'http://proxy.example.com:8080',
    'openai.vlmCaptioning.defaults.doSample': true,
    'openai.vlmCaptioning.defaults.seed': 42,
    'openai.vlmCaptioning.defaults.temperature': 0.7,
    'openai.vlmCaptioning.defaults.topP': 0.9,
    'openai.vlmCaptioning.defaults.presencePenalty': 0.5,
    'openai.vlmCaptioning.defaults.frequencyPenalty': 0.5,
    'openai.vlmCaptioning.defaults.maxCompletionTokens': 500,
  };

  const mockConfigGet = (key: string) => {
    return mockConfigValues[key];
  };

  beforeEach(async () => {
    // Create mocks
    const mockDatastoreService = {
      getFile: jest.fn().mockResolvedValue(Buffer.from('test-image-data')),
    };

    const mockConfigService = {
      get: jest.fn().mockImplementation(mockConfigGet),
    };

    const mockTemplateService = {
      getFrameCaptionTemplateWithoutObjects: jest.fn().mockReturnValue('Describe this image:'),
      getMultipleFrameCaptionTemplateWithoutObjects: jest.fn().mockReturnValue('Describe these images:'),
    };

    const mockOpenaiHelper = {
      initializeClient: jest.fn().mockReturnValue({
        client: new (OpenAI as any)(),
        openAiConfig: {},
        proxyAgent: {},
      }),
    };

    const mockFeaturesService = {
      hasFeature: jest.fn().mockReturnValue(true),
    };

    const mockInferenceCountService = {
      setVlmConfig: jest.fn(),
      incrementVlmProcessCount: jest.fn(),
      decrementVlmProcessCount: jest.fn(),
    };

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        VlmService,
        { provide: DatastoreService, useValue: mockDatastoreService },
        { provide: ConfigService, useValue: mockConfigService },
  { provide: TemplateService, useValue: mockTemplateService },
  { provide: OpenaiHelperService, useValue: mockOpenaiHelper },
  { provide: FeaturesService, useValue: mockFeaturesService },
  { provide: InferenceCountService, useValue: mockInferenceCountService },
      ],
    }).compile();

    service = module.get<VlmService>(VlmService);
    datastoreService = module.get(DatastoreService);
    configService = module.get(ConfigService);
    templateService = module.get(TemplateService);

    // Reset calls between tests
    jest.clearAllMocks();
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  describe('initialization', () => {
    it('should initialize the OpenAI client correctly', async () => {
      // Force initialization
      await (service as any).initialize();

  // Check that the OpenaiHelper.initializeClient was called and inference config set
  expect((service as any).$openAiHelper.initializeClient).toHaveBeenCalledWith('test-api-key', 'https://api.openai.com/v1');
  expect((service as any).$inferenceCount.setVlmConfig).toHaveBeenCalled();
    });

    it('should set the model from the available models', async () => {
      // Force initialization
      await (service as any).initialize();

      // Check if the model was set correctly
      expect(service.model).toBe('gpt-4-vision-preview');
    });

    it('should set serviceReady to true after successful initialization', async () => {
      // Force initialization
      await (service as any).initialize();

      // Check if serviceReady was set to true
      expect(service.serviceReady).toBe(true);
    });

    it('should set up proxy if URL is provided and host is not in noProxy', async () => {
      // Force initialization
      await (service as any).initialize();

  // Ensure OpenaiHelper initializeClient was invoked (it handles proxy internally)
  expect((service as any).$openAiHelper.initializeClient).toHaveBeenCalled();
    });
  });

  describe('defaultParams', () => {
    it('should return default parameters from config', () => {
      const params = (service as any).defaultParams();

      expect(params).toEqual({
        do_sample: true,
        seed: 42,
        temperature: 0.7,
        top_p: 0.9,
        presence_penalty: 0.5,
        frequency_penalty: 0.5,
        max_completion_tokens: 500,
      });
    });

    it('should handle missing config values', () => {
      // Mock config to return null for some values
      jest.spyOn(configService, 'get').mockImplementation((key) => {
        if (key === 'openai.vlmCaptioning.defaults.doSample') return null;
        return mockConfigValues[key];
      });

      const params = (service as any).defaultParams();
      expect(params.do_sample).toBeUndefined();
    });
  });

  describe('runTextOnlyInference', () => {
    it('should call OpenAI chat completions with correct parameters', async () => {
      const user_query = 'What is in this image?';
      const result = await service.runTextOnlyInference(user_query);

      expect(service.client.chat.completions.create).toHaveBeenCalledWith({
        messages: [
          {
            role: 'user',
            content: user_query,
          },
        ],
        model: expect.any(String),
        do_sample: true,
        seed: 42,
        temperature: 0.7,
        top_p: 0.9,
        presence_penalty: 0.5,
        frequency_penalty: 0.5,
        max_completion_tokens: 500,
      });
      
      expect(result).toBe('Mocked response content');
    });
  });

  describe('getInferenceConfig', () => {
    it('should return model info with device and model name', () => {
      service.model = 'gpt-4-vision-preview';
      const modelInfo = service.getInferenceConfig();
      
      expect(modelInfo).toEqual({
        device: 'CPU',
        model: 'gpt-4-vision-preview',
      });
    });
  });

  describe('imageInference', () => {
    it('should call OpenAI with correct image URLs and query', async () => {
      const userQuery = 'What is in this image?';
      const imageUri = ['https://example.com/image1.jpg', 'https://example.com/image2.jpg'];
      
      const result = await service.imageInference(userQuery, imageUri);
      
  expect(service.client.chat.completions.create).toHaveBeenCalledWith({
        messages: [
          {
            role: 'user',
            content: [
      { type: 'text', text: userQuery },
      { type: 'video', video: ['https://example.com/image1.jpg', 'https://example.com/image2.jpg'] },
            ],
          },
        ],
    model: service.model,
        do_sample: true,
        seed: 42,
        temperature: 0.7,
        top_p: 0.9,
        presence_penalty: 0.5,
        frequency_penalty: 0.5,
        max_completion_tokens: 500,
      });
      
      expect(result).toBe('Mocked response content');
    });

    it('should handle errors during image inference', async () => {
      // Mock the create method to throw an error
      jest.spyOn(service.client.chat.completions, 'create').mockRejectedValueOnce(new Error('API error'));
      
      const userQuery = 'What is in this image?';
      const imageUri = ['https://example.com/image.jpg'];
      
      await expect(service.imageInference(userQuery, imageUri)).rejects.toThrow('API error');
    });
  });

  describe('runSingleImage', () => {
    it('should encode image to base64 and call OpenAI API', async () => {
  // Mock the encodeBase64ContentFromUrl method (synchronous return expected by implementation)
  jest.spyOn(service as any, 'encodeBase64ContentFromUrl').mockReturnValueOnce('base64-encoded-image');
      
      const params = {
        fileNameOrUrl: 'test-image.jpg',
      };
      
      await service.runSingleImage(params);
      
      // Check if the encodeBase64ContentFromUrl was called
      expect((service as any).encodeBase64ContentFromUrl).toHaveBeenCalledWith('test-image.jpg');
      
      // Check if the OpenAI API was called with the correct parameters
      expect(service.client.chat.completions.create).toHaveBeenCalledWith({
        messages: [
          {
            role: 'user',
            content: [
              { type: 'text', text: 'Describe this image:' },
              { type: 'image_url', image_url: { url: 'data:image/jpeg;base64,base64-encoded-image' } },
            ],
          },
        ],
        model: expect.any(String),
        do_sample: true,
        seed: 42,
        temperature: 0.7,
        top_p: 0.9,
        presence_penalty: 0.5,
        frequency_penalty: 0.5,
        max_completion_tokens: 500,
      });
    });

    it('should use custom user query when provided', async () => {
  // Mock the encodeBase64ContentFromUrl method (synchronous return expected by implementation)
  jest.spyOn(service as any, 'encodeBase64ContentFromUrl').mockReturnValueOnce('base64-encoded-image');
      
      const params = {
        user_query: 'Custom query about this image:',
        fileNameOrUrl: 'test-image.jpg',
      };
      
      await service.runSingleImage(params);
      
      // Check if the OpenAI API was called with the custom query
      expect(service.client.chat.completions.create).toHaveBeenCalledWith(
        expect.objectContaining({
          messages: [
            {
              role: 'user',
              content: [
                { type: 'text', text: 'Custom query about this image:' },
                { type: 'image_url', image_url: { url: expect.stringContaining('base64-encoded-image') } },
              ],
            },
          ],
        })
      );
    });
  });

  describe('runMultiImage', () => {
    it('should encode multiple images and call OpenAI API', async () => {
      // Mock the encodeBase64ContentFromUrl method to return different values for different calls
      jest.spyOn(service as any, 'encodeBase64ContentFromUrl')
        .mockResolvedValueOnce('base64-encoded-image1')
        .mockResolvedValueOnce('base64-encoded-image2');
      
      const params = {
        fileNameOrUrl: ['image1.jpg', 'image2.jpg'],
      };
      
      await service.runMultiImage(params);
      
      // Check if the encodeBase64ContentFromUrl was called for each image
      expect((service as any).encodeBase64ContentFromUrl).toHaveBeenCalledTimes(2);
      expect((service as any).encodeBase64ContentFromUrl).toHaveBeenCalledWith('image1.jpg');
      expect((service as any).encodeBase64ContentFromUrl).toHaveBeenCalledWith('image2.jpg');
      
      // Check if the OpenAI API was called with the correct parameters
      expect(service.client.chat.completions.create).toHaveBeenCalledWith(
        expect.objectContaining({
          messages: [
            {
              role: 'user',
              content: expect.arrayContaining([
                { type: 'text', text: 'Describe these images:' },
                { type: 'image_url', image_url: { url: 'data:image/jpeg;base64,base64-encoded-image1' } },
                { type: 'image_url', image_url: { url: 'data:image/jpeg;base64,base64-encoded-image2' } },
              ]),
            },
          ],
        })
      );
    });
  });

  describe('encodeBase64ContentFromUrl', () => {
    it('should handle error when fetching content fails', async () => {
      // Since the implementation currently returns an empty string, we're just testing
      // that it doesn't throw an exception
      const result = await (service as any).encodeBase64ContentFromUrl('test-image.jpg');
      expect(result).toBe('');
    });
  });
});
