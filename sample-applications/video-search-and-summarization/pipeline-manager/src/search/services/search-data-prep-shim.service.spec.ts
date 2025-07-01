// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { Test, TestingModule } from '@nestjs/testing';
import { SearchDataPrepShimService } from './search-data-prep-shim.service';

describe('SearchDataPrepShimService', () => {
  let service: SearchDataPrepShimService;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [SearchDataPrepShimService],
    }).compile();

    service = module.get<SearchDataPrepShimService>(SearchDataPrepShimService);
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });
});
