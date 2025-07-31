// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Test, TestingModule } from '@nestjs/testing';
import { SearchShimService } from './search-shim.service';

describe('SearchShimService', () => {
  let service: SearchShimService;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [SearchShimService],
    }).compile();

    service = module.get<SearchShimService>(SearchShimService);
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });
});
