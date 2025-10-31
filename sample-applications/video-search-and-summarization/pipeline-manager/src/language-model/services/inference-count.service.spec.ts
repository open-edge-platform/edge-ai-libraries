// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Test, TestingModule } from '@nestjs/testing';
import { InferenceCountService } from './inference-count.service';
import { ConfigService } from '@nestjs/config';

describe('InferenceCountService', () => {
  let service: InferenceCountService;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        InferenceCountService,
        {
          provide: ConfigService,
          useValue: {
            get: jest.fn((key: string) => {
              const mockConfig = {
                'openai.vlmCaptioning.concurrent': 2,
                'openai.llmSummarization.concurrent': 3,
              };
              return mockConfig[key];
            }),
          },
        },
      ],
    }).compile();

    service = module.get<InferenceCountService>(InferenceCountService);
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  describe('Configuration Management', () => {
    describe('setVlmConfig', () => {
      it('should set VLM config and trigger equality check', () => {
        const consoleSpy = jest.spyOn(console, 'log').mockImplementation();
        const mockConfig = { model: 'vlm-model', ip: '192.168.1.1' };

        service.setVlmConfig(mockConfig);

        expect(consoleSpy).toHaveBeenCalledWith('EQUALITY', false);
        consoleSpy.mockRestore();
      });
    });

    describe('setLlmConfig', () => {
      it('should set LLM config and trigger equality check', () => {
        const consoleSpy = jest.spyOn(console, 'log').mockImplementation();
        const mockConfig = { model: 'llm-model', ip: '192.168.1.2' };

        service.setLlmConfig(mockConfig);

        expect(consoleSpy).toHaveBeenCalledWith('EQUALITY', false);
        consoleSpy.mockRestore();
      });
    });

    describe('configEqualityCheck', () => {
      it('should set useVlmForInference to true when configs are equal', () => {
        const consoleSpy = jest.spyOn(console, 'log').mockImplementation();
        const sameConfig = { model: 'same-model', ip: '192.168.1.1' };

        service.setVlmConfig(sameConfig);
        service.setLlmConfig(sameConfig);

        expect(consoleSpy).toHaveBeenCalledWith('EQUALITY', true);
        consoleSpy.mockRestore();
      });

      it('should set useVlmForInference to false when configs are different', () => {
        const consoleSpy = jest.spyOn(console, 'log').mockImplementation();
        const vlmConfig = { model: 'vlm-model', ip: '192.168.1.1' };
        const llmConfig = { model: 'llm-model', ip: '192.168.1.2' };

        service.setVlmConfig(vlmConfig);
        service.setLlmConfig(llmConfig);

        expect(consoleSpy).toHaveBeenCalledWith('EQUALITY', false);
        consoleSpy.mockRestore();
      });

      it('should set useVlmForInference to false when only VLM config is set', () => {
        const consoleSpy = jest.spyOn(console, 'log').mockImplementation();
        const vlmConfig = { model: 'vlm-model', ip: '192.168.1.1' };

        service.setVlmConfig(vlmConfig);

        expect(consoleSpy).toHaveBeenCalledWith('EQUALITY', false);
        consoleSpy.mockRestore();
      });

      it('should set useVlmForInference to false when only LLM config is set', () => {
        const consoleSpy = jest.spyOn(console, 'log').mockImplementation();
        const llmConfig = { model: 'llm-model', ip: '192.168.1.2' };

        service.setLlmConfig(llmConfig);

        expect(consoleSpy).toHaveBeenCalledWith('EQUALITY', false);
        consoleSpy.mockRestore();
      });
    });
  });

  describe('Count Tracking', () => {
    describe('getVlmCount', () => {
      it('should return initial VLM count as 0', () => {
        expect(service.getVlmCount()).toBe(0);
      });

      it('should return correct VLM count after increments', () => {
        service.incrementVlmProcessCount();
        service.incrementVlmProcessCount();

        expect(service.getVlmCount()).toBe(2);
      });
    });

    describe('getLlmCount', () => {
      it('should return initial LLM count as 0', () => {
        expect(service.getLlmCount()).toBe(0);
      });

      it('should return correct LLM count after increments', () => {
        service.incrementLlmProcessCount();
        service.incrementLlmProcessCount();

        expect(service.getLlmCount()).toBe(2);
      });
    });

    describe('incrementVlmProcessCount', () => {
      it('should increment VLM process count', () => {
        const initialCount = service.getVlmCount();
        service.incrementVlmProcessCount();

        expect(service.getVlmCount()).toBe(initialCount + 1);
      });
    });

    describe('incrementLlmProcessCount', () => {
      it('should increment only LLM count when configs are different', () => {
        const vlmConfig = { model: 'vlm-model', ip: '192.168.1.1' };
        const llmConfig = { model: 'llm-model', ip: '192.168.1.2' };
        service.setVlmConfig(vlmConfig);
        service.setLlmConfig(llmConfig);

        const initialVlmCount = service.getVlmCount();
        const initialLlmCount = service.getLlmCount();
        
        service.incrementLlmProcessCount();

        expect(service.getVlmCount()).toBe(initialVlmCount);
        expect(service.getLlmCount()).toBe(initialLlmCount + 1);
      });

      it('should increment both VLM and LLM count when configs are same', () => {
        const sameConfig = { model: 'same-model', ip: '192.168.1.1' };
        service.setVlmConfig(sameConfig);
        service.setLlmConfig(sameConfig);

        const initialVlmCount = service.getVlmCount();
        const initialLlmCount = service.getLlmCount();
        
        service.incrementLlmProcessCount();

        expect(service.getVlmCount()).toBe(initialVlmCount + 1);
        expect(service.getLlmCount()).toBe(initialLlmCount + 1);
      });
    });

    describe('decrementVlmProcessCount', () => {
      it('should decrement VLM process count when count is greater than 0', () => {
        service.incrementVlmProcessCount();
        service.incrementVlmProcessCount();
        const currentCount = service.getVlmCount();

        service.decrementVlmProcessCount();

        expect(service.getVlmCount()).toBe(currentCount - 1);
      });

      it('should not decrement VLM count below 0', () => {
        service.decrementVlmProcessCount();

        expect(service.getVlmCount()).toBe(0);
      });
    });

    describe('decrementLlmProcessCount', () => {
      it('should decrement only LLM count when configs are different', () => {
        const vlmConfig = { model: 'vlm-model', ip: '192.168.1.1' };
        const llmConfig = { model: 'llm-model', ip: '192.168.1.2' };
        service.setVlmConfig(vlmConfig);
        service.setLlmConfig(llmConfig);
        
        service.incrementLlmProcessCount();
        service.incrementVlmProcessCount();

        const vlmCountBefore = service.getVlmCount();
        const llmCountBefore = service.getLlmCount();

        service.decrementLlmProcessCount();

        expect(service.getVlmCount()).toBe(vlmCountBefore);
        expect(service.getLlmCount()).toBe(llmCountBefore - 1);
      });

      it('should decrement both VLM and LLM count when configs are same', () => {
        const sameConfig = { model: 'same-model', ip: '192.168.1.1' };
        service.setVlmConfig(sameConfig);
        service.setLlmConfig(sameConfig);
        
        service.incrementLlmProcessCount();

        const vlmCountBefore = service.getVlmCount();
        const llmCountBefore = service.getLlmCount();

        service.decrementLlmProcessCount();

        expect(service.getVlmCount()).toBe(vlmCountBefore - 1);
        expect(service.getLlmCount()).toBe(llmCountBefore - 1);
      });

      it('should not decrement LLM count below 0', () => {
        service.decrementLlmProcessCount();

        expect(service.getLlmCount()).toBe(0);
      });
    });
  });

  describe('Slot Availability', () => {
    describe('hasVlmSlots', () => {
      it('should return true when VLM count is below max concurrent', () => {
        // maxVlmConcurrent is 2 from config
        expect(service.hasVlmSlots()).toBe(true);

        service.incrementVlmProcessCount();
        expect(service.hasVlmSlots()).toBe(true);
      });

      it('should return false when VLM count reaches max concurrent', () => {
        // maxVlmConcurrent is 2 from config
        service.incrementVlmProcessCount();
        service.incrementVlmProcessCount();

        expect(service.hasVlmSlots()).toBe(false);
      });
    });

    describe('hasLlmSlots', () => {
      it('should return true when LLM count is below max and configs are different', () => {
        const vlmConfig = { model: 'vlm-model', ip: '192.168.1.1' };
        const llmConfig = { model: 'llm-model', ip: '192.168.1.2' };
        service.setVlmConfig(vlmConfig);
        service.setLlmConfig(llmConfig);

        // maxLlmConcurrent is 3 from config
        expect(service.hasLlmSlots()).toBe(true);

        service.incrementLlmProcessCount();
        service.incrementLlmProcessCount();
        expect(service.hasLlmSlots()).toBe(true);
      });

      it('should return false when LLM count reaches max and configs are different', () => {
        const vlmConfig = { model: 'vlm-model', ip: '192.168.1.1' };
        const llmConfig = { model: 'llm-model', ip: '192.168.1.2' };
        service.setVlmConfig(vlmConfig);
        service.setLlmConfig(llmConfig);

        // maxLlmConcurrent is 3 from config
        service.incrementLlmProcessCount();
        service.incrementLlmProcessCount();
        service.incrementLlmProcessCount();

        expect(service.hasLlmSlots()).toBe(false);
      });

      it('should use VLM slots when configs are same', () => {
        const sameConfig = { model: 'same-model', ip: '192.168.1.1' };
        service.setVlmConfig(sameConfig);
        service.setLlmConfig(sameConfig);

        // Should use VLM slots (max 2) instead of LLM slots (max 3)
        expect(service.hasLlmSlots()).toBe(true);

        service.incrementLlmProcessCount(); // This increments both VLM and LLM
        expect(service.hasLlmSlots()).toBe(true);

        service.incrementLlmProcessCount(); // This should hit VLM limit
        expect(service.hasLlmSlots()).toBe(false);
      });
    });
  });

  describe('Integration Tests', () => {
    it('should handle complex scenario with mixed increments and decrements', () => {
      const sameConfig = { model: 'same-model', ip: '192.168.1.1' };
      service.setVlmConfig(sameConfig);
      service.setLlmConfig(sameConfig);

      // Increment both types
      service.incrementVlmProcessCount();
      service.incrementLlmProcessCount(); // This also increments VLM

      expect(service.getVlmCount()).toBe(2); // 1 + 1 (from LLM increment)
      expect(service.getLlmCount()).toBe(1);
      expect(service.hasVlmSlots()).toBe(false); // At max VLM capacity
      expect(service.hasLlmSlots()).toBe(false); // Uses VLM slots

      // Decrement LLM
      service.decrementLlmProcessCount(); // This also decrements VLM

      expect(service.getVlmCount()).toBe(1);
      expect(service.getLlmCount()).toBe(0);
      expect(service.hasVlmSlots()).toBe(true);
      expect(service.hasLlmSlots()).toBe(true);
    });

    it('should handle config changes during runtime', () => {
      // Start with different configs
      const vlmConfig = { model: 'vlm-model', ip: '192.168.1.1' };
      const llmConfig = { model: 'llm-model', ip: '192.168.1.2' };
      service.setVlmConfig(vlmConfig);
      service.setLlmConfig(llmConfig);

      service.incrementLlmProcessCount();
      expect(service.getVlmCount()).toBe(0);
      expect(service.getLlmCount()).toBe(1);

      // Change to same configs
      const newConfig = { model: 'unified-model', ip: '192.168.1.100' };
      service.setVlmConfig(newConfig);
      service.setLlmConfig(newConfig);

      // New LLM increment should now also increment VLM
      service.incrementLlmProcessCount();
      expect(service.getVlmCount()).toBe(1);
      expect(service.getLlmCount()).toBe(2);
    });
  });
});
