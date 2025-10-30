// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import * as request from 'supertest';
import { App } from 'supertest/types';
import { AppController } from '../src/app.controller';
import { AppConfigService } from '../src/video-upload/services/app-config.service';
import { FeaturesService } from '../src/features/features.service';

describe('AppController (e2e)', () => {
  let app: INestApplication<App>;

  beforeEach(async () => {
    // Use a minimal module instead of the full AppModule to avoid database/external service connections
    const moduleFixture: TestingModule = await Test.createTestingModule({
      controllers: [AppController],
      providers: [
        {
          provide: AppConfigService,
          useValue: {
            systemConfigWithMeta: jest.fn().mockResolvedValue({
              systemConfig: { 
                frameOverlap: 1,
                multiFrame: 3,
                evamPipeline: 'test-pipeline'
              },
              meta: { version: '1.0.0' }
            })
          }
        },
        {
          provide: FeaturesService,
          useValue: {
            getFeatures: jest.fn().mockReturnValue({
              videoUpload: true,
              search: true,
              summary: true
            })
          }
        }
      ]
    }).compile();

    app = moduleFixture.createNestApplication();
    await app.init();
  });

  afterEach(async () => {
    if (app) {
      await app.close();
    }
  });

  it('should be defined', () => {
    expect(app).toBeDefined();
  });

  it('should have app controller defined', () => {
    const appController = app.get(AppController);
    expect(appController).toBeDefined();
  });
});
