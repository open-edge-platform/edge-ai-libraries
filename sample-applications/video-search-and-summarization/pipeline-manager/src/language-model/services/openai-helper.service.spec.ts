// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Test, TestingModule } from '@nestjs/testing';
import { OpenaiHelperService } from './openai-helper.service';
import { ConfigService } from '@nestjs/config';

describe('OpenaiHelperService', () => {
  let service: OpenaiHelperService;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        OpenaiHelperService,
        {
          provide: ConfigService,
          useValue: {
            get: jest.fn((key: string) => {
              const config = {
                'proxy.url': undefined,
                'proxy.noProxy': '',
              };
              return config[key];
            }),
          },
        },
      ],
    }).compile();

    service = module.get<OpenaiHelperService>(OpenaiHelperService);
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  it('should build config URL from base URL host and port', () => {
    expect(
      service.getConfigUrl(
        { baseURL: 'http://ovms:8300/v3' },
        'v1/config',
      ),
    ).toBe('http://ovms:8300/v1/config');
  });

  it('should select configured model when available', () => {
    expect(
      service.selectModel({
        availableModels: ['llm-a', 'vlm-b'],
        configuredModelName: 'vlm-b',
        configuredModelEnv: 'VLM_MODEL_NAME',
        serviceLabel: 'VLM captioning',
      }),
    ).toBe('vlm-b');
  });

  it('should auto-select the only available model', () => {
    expect(
      service.selectModel({
        availableModels: ['shared-vlm'],
        configuredModelEnv: 'VLM_MODEL_NAME',
        serviceLabel: 'VLM captioning',
      }),
    ).toBe('shared-vlm');
  });

  it('should fail when multiple models are available without explicit selection', () => {
    expect(() =>
      service.selectModel({
        availableModels: ['llm-a', 'vlm-b'],
        configuredModelEnv: 'LLM_MODEL_NAME',
        serviceLabel: 'LLM summarization',
      }),
    ).toThrow(
      'Multiple models are available for LLM summarization. Configure LLM_MODEL_NAME.',
    );
  });

  it('should use fallback model when multiple models exist and no explicit config', () => {
    // Simulates shared-model mode: LLM_MODEL_NAME not set, but VLM_MODEL_NAME is set.
    // LLM service should fall back to using the VLM model.
    expect(
      service.selectModel({
        availableModels: ['Intel/neural-chat-7b', 'Qwen/Qwen2.5-VL-3B'],
        configuredModelEnv: 'LLM_MODEL_NAME',
        serviceLabel: 'LLM summarization',
        fallbackModelName: 'Qwen/Qwen2.5-VL-3B',
      }),
    ).toBe('Qwen/Qwen2.5-VL-3B');
  });

  it('should fail when fallback model is not in available models', () => {
    expect(() =>
      service.selectModel({
        availableModels: ['Intel/neural-chat-7b', 'other-model'],
        configuredModelEnv: 'LLM_MODEL_NAME',
        serviceLabel: 'LLM summarization',
        fallbackModelName: 'Qwen/Qwen2.5-VL-3B', // not in available models
      }),
    ).toThrow(
      'Multiple models are available for LLM summarization. Configure LLM_MODEL_NAME.',
    );
  });

  it('should prefer explicit config over fallback', () => {
    expect(
      service.selectModel({
        availableModels: ['Intel/neural-chat-7b', 'Qwen/Qwen2.5-VL-3B'],
        configuredModelName: 'Intel/neural-chat-7b',
        configuredModelEnv: 'LLM_MODEL_NAME',
        serviceLabel: 'LLM summarization',
        fallbackModelName: 'Qwen/Qwen2.5-VL-3B',
      }),
    ).toBe('Intel/neural-chat-7b');
  });

  it('should reject a disallowed single model fallback', () => {
    expect(() =>
      service.selectModel({
        availableModels: ['llm-only'],
        configuredModelEnv: 'VLM_MODEL_NAME',
        serviceLabel: 'VLM captioning',
        disallowedSingleModelName: 'llm-only',
        disallowedSingleModelReason:
          'VLM captioning requires VLM_MODEL_NAME when OVMS is configured with only the LLM model.',
      }),
    ).toThrow(
      'VLM captioning requires VLM_MODEL_NAME when OVMS is configured with only the LLM model.',
    );
  });
});
