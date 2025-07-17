// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Test, TestingModule } from '@nestjs/testing';
import { DataPrepShimService } from './data-prep-shim.service';

describe('DataPrepShimService', () => {
  let service: DataPrepShimService;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [DataPrepShimService],
    }).compile();

    service = module.get<DataPrepShimService>(DataPrepShimService);
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });
});
