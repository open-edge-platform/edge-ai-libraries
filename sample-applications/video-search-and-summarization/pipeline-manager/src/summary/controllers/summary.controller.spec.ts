// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Test, TestingModule } from '@nestjs/testing';
import { SummaryController } from './summary.controller';

describe('SummaryController', () => {
  let controller: SummaryController;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      controllers: [SummaryController],
    }).compile();

    controller = module.get<SummaryController>(SummaryController);
  });

  it('should be defined', () => {
    expect(controller).toBeDefined();
  });
});
