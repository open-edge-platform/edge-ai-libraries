// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Test, TestingModule } from '@nestjs/testing';
import { SearchDbService } from './search-db.service';

describe('SearchDbService', () => {
  let service: SearchDbService;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [SearchDbService],
    }).compile();

    service = module.get<SearchDbService>(SearchDbService);
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });
});
