// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { ConfigService } from '@nestjs/config';
import { Test, TestingModule } from '@nestjs/testing';
import { HttpsProxyAgent } from 'https-proxy-agent';
import { OpenAI } from 'openai';
import { Subject } from 'rxjs';
import { ServiceUnavailableException } from '@nestjs/common';
import { LlmService } from './llm.service';
import { TemplateService } from './template.service';

// Mock OpenAI
jest.mock('openai', () => {
  const mockChatCompletionCreate = jest.fn();
  const mockModelsList = jest.fn();
  return {
    OpenAI: jest.fn().mockImplementation(() => ({
      chat: {
        completions: {
          create: mockChatCompletionCreate,
        },
      },
      models: {
        list: mockModelsList,
      },
    })),
  };
});

// Mock HttpsProxyAgent
jest.mock('https-proxy-agent', () => ({
  HttpsProxyAgent: jest.fn(),
}));

describe('LlmService', () => {
  let service: LlmService;
  let configService: ConfigService;
  let templateService: TemplateService;
  let mockFetch: jest.Mock;
  let mockClientCompletionCreate: jest.Mock;
  let mockClientModelsList: jest.Mock;

  // Mock response data
  const mockModelConfigResponse = {
    'test-model': {
      model_version_status: [
        {
          version: '1.0',
          state: 'AVAILABLE',
          status: {
            error_code: '',
            error_message: '',
          },
        },
      ],
    },
  };

  // Mock config values
  const mockConfig = {
    'openai.llmSummarization.apiKey': 'mock-api-key',
    'openai.llmSummarization.apiBase': 'https://api.mock.com',
    'openai.llmSummarization.modelsAPI': 'models',
    'openai.llmSummarization.device': 'CPU',
    'openai.llmSummarization.defaults.doSample': true,
    'openai.llmSummarization.defaults.seed': 42,
    'openai.llmSummarization.defaults.temperature': 0.7,
    'openai.llmSummarization.defaults.topP': 0.95,
    'openai.llmSummarization.defaults.presencePenalty': 0.5,
    'openai.llmSummarization.defaults.frequencyPenalty': 0.5,
    'openai.llmSummarization.defaults.maxCompletionTokens': 500,
    'openai.llmSummarization.maxContextLength': 10000,
    'openai.llmSummarization.concurrent': 2,
    'proxy.url': 'http://proxy.example.com',
    'proxy.noProxy': '',
  };

  beforeEach(async () => {
    // Mock fetch
    mockFetch = jest.fn().mockImplementation(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve(mockModelConfigResponse),
      }),
    );
    global.fetch = mockFetch;

    // Mock client methods
    mockClientCompletionCreate = jest.fn();
    mockClientModelsList = jest.fn();

    // Set up mocks
    (OpenAI as unknown as jest.Mock).mockImplementation(() => ({
      chat: {
        completions: {
          create: mockClientCompletionCreate,
        },
      },
      models: {
        list: mockClientModelsList,
      },
    }));

    // Mock ConfigService
    configService = {
      get: jest.fn((key) => mockConfig[key]),
    } as unknown as ConfigService;

    // Mock TemplateService
    templateService = {
      createUserQuery: jest.fn().mockImplementation((template, data) => {
        if (Array.isArray(data)) {
          return `Template: ${template}, Data: ${data.join(',')}`;
        }
        return `Template: ${template}, Data: ${data}`;
      }),
    } as unknown as TemplateService;

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        LlmService,
        {
          provide: ConfigService,
          useValue: configService,
        },
        {
          provide: TemplateService,
          useValue: templateService,
        },
      ],
    }).compile();

    service = module.get<LlmService>(LlmService);
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  describe('initialization', () => {
    it('should initialize the service with the model from config endpoint', async () => {
      expect(service.serviceReady).toBeTruthy();
      expect(service.model).toBe('test-model');
      expect(mockFetch).toHaveBeenCalled();
    });

    it('should use proxy if configured', async () => {
      // Re-test with a mock implementation that checks for proxy
      await service['initialize']();
      expect(HttpsProxyAgent).toHaveBeenCalledWith('http://proxy.example.com');
    });

    it('should fallback to models API if config endpoint fails', async () => {
      // Mock failure of config endpoint
      mockFetch.mockRejectedValueOnce(new Error('Failed to fetch'));

      // Mock successful models list
      mockClientModelsList.mockResolvedValueOnce({
        data: [{ id: 'fallback-model' }],
      });

      // Re-initialize service
      await service['initialize']();

      expect(mockClientModelsList).toHaveBeenCalled();
      expect(service.model).toBe('fallback-model');
    });

    it('should throw if both initialization methods fail', async () => {
      // Mock failures
      mockFetch.mockRejectedValueOnce(new Error('Failed to fetch'));
      mockClientModelsList.mockRejectedValueOnce(
        new Error('Failed to list models'),
      );

      await expect(service['initialize']()).rejects.toThrow(
        ServiceUnavailableException,
      );
    });
  });

  describe('getInferenceConfig', () => {
    it('should return device and model information', () => {
      const config = service.getInferenceConfig();
      expect(config).toEqual({
        device: 'CPU',
        model: 'test-model',
      });
    });
  });

  describe('defaultParams', () => {
    it('should return correct default parameters from config', () => {
      const params = service['defaultParams']();
      expect(params).toEqual({
        do_sample: true,
        seed: 42,
        temperature: 0.7,
        top_p: 0.95,
        presence_penalty: 0.5,
        frequency_penalty: 0.5,
        max_completion_tokens: 500,
        max_tokens: 500,
      });
    });

    it('should handle missing config values', () => {
      // Mock config to return null for some values
      jest.spyOn(configService, 'get').mockImplementation((key) => {
        if (key === 'openai.llmSummarization.defaults.doSample') return null;
        return mockConfig[key];
      });

      const params = service['defaultParams']();
      expect(params).not.toHaveProperty('do_sample');
    });
  });

  describe('generateResponse', () => {
    it('should return response content from chat completion', async () => {
      const mockResponse = {
        choices: [
          {
            message: {
              content: 'This is a test response',
            },
          },
        ],
      };

      mockClientCompletionCreate.mockResolvedValueOnce(mockResponse);

      const result = await service.generateResponse('Test query').toPromise();
      expect(result).toBe('This is a test response');
      expect(mockClientCompletionCreate).toHaveBeenCalledWith({
        messages: [{ role: 'user', content: 'Test query' }],
        model: 'test-model',
        do_sample: true,
        seed: 42,
        temperature: 0.7,
        top_p: 0.95,
        presence_penalty: 0.5,
        frequency_penalty: 0.5,
        max_completion_tokens: 500,
        max_tokens: 500,
        stream: false,
      });
    });

    it('should return null if response has no content', async () => {
      const mockResponse = {
        choices: [
          {
            message: {
              content: null,
            },
          },
        ],
      };

      mockClientCompletionCreate.mockResolvedValueOnce(mockResponse);

      const result = await service.generateResponse('Test query').toPromise();
      expect(result).toBeNull();
    });
  });

  describe('generateStreamingResponse', () => {
    it('should stream response chunks', async () => {
      const streamer = new Subject<string>();
      const streamSpy = jest.spyOn(streamer, 'next');
      const completeSpy = jest.spyOn(streamer, 'complete');

      // Mock async generator for streaming
      const mockChunks = [
        { choices: [{ delta: { content: 'Chunk' } }] },
        { choices: [{ delta: { content: ' of' } }] },
        { choices: [{ delta: { content: ' text' } }] },
      ];

      mockClientCompletionCreate.mockResolvedValueOnce({
        [Symbol.asyncIterator]: async function* () {
          for (const chunk of mockChunks) {
            yield chunk;
          }
        },
      });

      await service.generateStreamingResponse('Test query', streamer);

      expect(streamSpy).toHaveBeenCalledWith('Chunk');
      expect(streamSpy).toHaveBeenCalledWith(' of');
      expect(streamSpy).toHaveBeenCalledWith(' text');
      expect(completeSpy).toHaveBeenCalled();
    });

    it('should handle stream chunks without content', async () => {
      const streamer = new Subject<string>();
      const streamSpy = jest.spyOn(streamer, 'next');

      // Mock async generator with some empty content
      const mockChunks = [
        { choices: [{ delta: { content: 'Text' } }] },
        { choices: [{ delta: {} }] },
        { choices: [{ delta: { content: null } }] },
      ];

      mockClientCompletionCreate.mockResolvedValueOnce({
        [Symbol.asyncIterator]: async function* () {
          for (const chunk of mockChunks) {
            yield chunk;
          }
        },
      });

      await service.generateStreamingResponse('Test query', streamer);
      expect(streamSpy).toHaveBeenCalledTimes(1); // Only once with actual content
    });
  });

  describe('runTextOnlyInference', () => {
    it('should return text response for non-streaming mode', async () => {
      const mockResponse = {
        choices: [
          {
            message: {
              content: 'Inference result',
            },
          },
        ],
      };

      mockClientCompletionCreate.mockResolvedValueOnce(mockResponse);

      const result = await service.runTextOnlyInference(
        'Test inference',
        false,
      );

      expect(result).toBe('Inference result');
      expect(mockClientCompletionCreate).toHaveBeenCalledWith({
        messages: [{ role: 'user', content: 'Test inference' }],
        model: 'test-model',
        do_sample: true,
        seed: 42,
        temperature: 0.7,
        top_p: 0.95,
        presence_penalty: 0.5,
        frequency_penalty: 0.5,
        max_completion_tokens: 500,
        max_tokens: 500,
      });
    });

    it('should return generator for streaming mode', async () => {
      // Mock async generator for streaming
      const mockChunks = [
        { choices: [{ delta: { content: 'Streaming' } }] },
        { choices: [{ delta: { content: ' result' } }] },
      ];

      mockClientCompletionCreate.mockResolvedValueOnce({
        [Symbol.asyncIterator]: async function* () {
          for (const chunk of mockChunks) {
            yield chunk;
          }
        },
      });

      const generator = await service.runTextOnlyInference(
        'Test streaming',
        true,
      );

      // Verify it's a generator
      expect(typeof generator).toBe('object');

      // Test streaming by collecting all chunks
      if (generator && typeof generator !== 'string') {
        const chunks: string[] = [];
        for await (const chunk of generator) {
          chunks.push(chunk);
        }
        expect(chunks).toEqual(['Streaming', ' result']);
      }

      expect(mockClientCompletionCreate).toHaveBeenCalledWith({
        messages: [{ role: 'user', content: 'Test streaming' }],
        model: 'test-model',
        do_sample: true,
        seed: 42,
        temperature: 0.7,
        top_p: 0.95,
        presence_penalty: 0.5,
        frequency_penalty: 0.5,
        max_completion_tokens: 500,
        max_tokens: 500,
        stream: true,
      });
    });
  });

  describe('summarizeMapReduce', () => {
    it('should generate single-pass summary when text fits in context length', async () => {
      const texts = ['Short text 1', 'Short text 2'];
      const streamer = new Subject<string>();
      const streamSpy = jest.spyOn(streamer, 'next');

      // Mock streaming response
      const mockChunks = [
        { choices: [{ delta: { content: 'Summary' } }] },
        { choices: [{ delta: { content: ' of texts' } }] },
      ];

      mockClientCompletionCreate.mockResolvedValueOnce({
        [Symbol.asyncIterator]: async function* () {
          for (const chunk of mockChunks) {
            yield chunk;
          }
        },
      });

      await service.summarizeMapReduce(
        texts,
        'summarizeTemplate',
        'reduceTemplate',
        'reduceSingleTextTemplate',
        streamer,
      );

      expect(templateService.createUserQuery).toHaveBeenCalledWith(
        'summarizeTemplate',
        texts,
      );
      expect(streamSpy).toHaveBeenCalledWith('Summary');
      expect(streamSpy).toHaveBeenCalledWith(' of texts');
    });
  });
});
