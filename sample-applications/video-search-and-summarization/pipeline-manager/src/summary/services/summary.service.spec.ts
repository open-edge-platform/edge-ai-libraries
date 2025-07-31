// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Test, TestingModule } from '@nestjs/testing';
import { SummaryService } from './summary.service';

describe('SummaryService', () => {
  let service: SummaryService;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [SummaryService],
    }).compile();

    service = module.get<SummaryService>(SummaryService);
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });
});
