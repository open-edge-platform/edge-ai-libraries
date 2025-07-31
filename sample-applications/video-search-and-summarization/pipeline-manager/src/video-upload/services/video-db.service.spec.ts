// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Test, TestingModule } from '@nestjs/testing';
import { VideoDbService } from './video-db.service';

describe('VideoDbService', () => {
  let service: VideoDbService;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [VideoDbService],
    }).compile();

    service = module.get<VideoDbService>(VideoDbService);
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });
});
