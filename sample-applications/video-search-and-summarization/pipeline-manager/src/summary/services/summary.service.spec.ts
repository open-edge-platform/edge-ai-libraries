// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Test, TestingModule } from '@nestjs/testing';
import { SummaryService } from './summary.service';
import { StateService } from '../../state-manager/services/state.service';

describe('SummaryService', () => {
  let service: SummaryService;
  let stateService: jest.Mocked<StateService>;

  beforeEach(async () => {
    const stateServiceMock = {
      remove: jest.fn(),
      fetch: jest.fn(),
      create: jest.fn(),
      update: jest.fn(),
    };

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        SummaryService,
        { provide: StateService, useValue: stateServiceMock },
      ],
    }).compile();

    service = module.get<SummaryService>(SummaryService);
    stateService = module.get(StateService) as jest.Mocked<StateService>;

    // Reset mocks
    jest.clearAllMocks();
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  describe('removeSummary', () => {
    it('should successfully remove summary and return true', async () => {
      const stateId = 'test-state-id';
      
      stateService.remove.mockResolvedValue(undefined);

      const result = await service.removeSummary(stateId);

      expect(stateService.remove).toHaveBeenCalledWith(stateId);
      expect(result).toBe(true);
    });

    it('should handle state service errors during removal', async () => {
      const stateId = 'error-state-id';
      
      stateService.remove.mockRejectedValue(new Error('State removal failed'));

      await expect(service.removeSummary(stateId)).rejects.toThrow('State removal failed');

      expect(stateService.remove).toHaveBeenCalledWith(stateId);
    });

    it('should return true even when removing non-existent state', async () => {
      const stateId = 'non-existent-state-id';
      
      stateService.remove.mockResolvedValue(undefined);

      const result = await service.removeSummary(stateId);

      expect(stateService.remove).toHaveBeenCalledWith(stateId);
      expect(result).toBe(true);
    });

    it('should handle empty string stateId', async () => {
      const stateId = '';
      
      stateService.remove.mockResolvedValue(undefined);

      const result = await service.removeSummary(stateId);

      expect(stateService.remove).toHaveBeenCalledWith(stateId);
      expect(result).toBe(true);
    });

    it('should handle null-like values gracefully', async () => {
      const stateId = 'null-test';
      
      stateService.remove.mockResolvedValue(null as any);

      const result = await service.removeSummary(stateId);

      expect(stateService.remove).toHaveBeenCalledWith(stateId);
      expect(result).toBe(true);
    });

    it('should handle network timeout errors', async () => {
      const stateId = 'timeout-state-id';
      
      stateService.remove.mockRejectedValue(new Error('Request timeout'));

      await expect(service.removeSummary(stateId)).rejects.toThrow('Request timeout');

      expect(stateService.remove).toHaveBeenCalledWith(stateId);
    });

    it('should handle concurrent removal requests', async () => {
      const stateId1 = 'concurrent-state-1';
      const stateId2 = 'concurrent-state-2';
      
      stateService.remove.mockResolvedValue(undefined);

      const [result1, result2] = await Promise.all([
        service.removeSummary(stateId1),
        service.removeSummary(stateId2),
      ]);

      expect(stateService.remove).toHaveBeenCalledTimes(2);
      expect(stateService.remove).toHaveBeenCalledWith(stateId1);
      expect(stateService.remove).toHaveBeenCalledWith(stateId2);
      expect(result1).toBe(true);
      expect(result2).toBe(true);
    });

    it('should handle special characters in stateId', async () => {
      const stateId = 'test-state-@#$%^&*()_+-={}[]|\\:";\'<>?,./';
      
      stateService.remove.mockResolvedValue(undefined);

      const result = await service.removeSummary(stateId);

      expect(stateService.remove).toHaveBeenCalledWith(stateId);
      expect(result).toBe(true);
    });

    it('should handle very long stateId', async () => {
      const stateId = 'a'.repeat(1000); // Very long ID
      
      stateService.remove.mockResolvedValue(undefined);

      const result = await service.removeSummary(stateId);

      expect(stateService.remove).toHaveBeenCalledWith(stateId);
      expect(result).toBe(true);
    });
  });
});
