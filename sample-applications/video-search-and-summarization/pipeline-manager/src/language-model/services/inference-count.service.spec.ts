// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Test, TestingModule } from '@nestjs/testing';
import { InferenceCountService } from './inference-count.service';

describe('InferenceCountService', () => {
  let service: InferenceCountService;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [InferenceCountService],
    }).compile();

    service = module.get<InferenceCountService>(InferenceCountService);
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });
});
