// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Test, TestingModule } from '@nestjs/testing';
import { AppController } from './app.controller';
import { AppConfigService } from './video-upload/services/app-config.service';

describe('AppController', () => {
  let appController: AppController;
  let appConfigService: AppConfigService;

  beforeEach(async () => {
    const mockAppConfigService = {
      systemConfigWithMeta: jest.fn().mockResolvedValue({
        version: '1.0.0',
        environment: 'development',
      }),
    };

    const app: TestingModule = await Test.createTestingModule({
      controllers: [AppController],
      providers: [
        {
          provide: AppConfigService,
          useValue: mockAppConfigService,
        },
      ],
    }).compile();

    appController = app.get<AppController>(AppController);
    appConfigService = app.get<AppConfigService>(AppConfigService);
  });

  it('should be defined', () => {
    expect(appController).toBeDefined();
  });

  describe('getSystemConfig', () => {
    it('should return system configuration with metadata', async () => {
      const result = {
        version: '1.0.0',
        environment: 'development',
      };

      const response = await appController.getSystemConfig();
      expect(response).toEqual(result);
      expect(appConfigService.systemConfigWithMeta).toHaveBeenCalled();
    });
  });
});
