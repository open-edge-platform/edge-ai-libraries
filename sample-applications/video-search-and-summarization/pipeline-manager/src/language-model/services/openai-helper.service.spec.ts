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
});
