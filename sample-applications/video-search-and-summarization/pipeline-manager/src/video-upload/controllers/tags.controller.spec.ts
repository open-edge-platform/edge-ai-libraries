// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Test, TestingModule } from '@nestjs/testing';
import { TagsController } from './tags.controller';
import { TagsService } from '../services/tags.service';
import { TagsDbService } from '../services/tags-db.service';

describe('TagsController', () => {
  let controller: TagsController;
  let tagsService: jest.Mocked<TagsService>;
  let tagsDbService: jest.Mocked<TagsDbService>;

  beforeEach(async () => {
    const tagsServiceMock = {
      create: jest.fn(),
      findAll: jest.fn(),
      findOne: jest.fn(),
      update: jest.fn(),
      remove: jest.fn(),
    };

    const tagsDbServiceMock = {
      create: jest.fn(),
      createMany: jest.fn(),
      readAll: jest.fn(),
      read: jest.fn(),
      remove: jest.fn(),
    };

    const module: TestingModule = await Test.createTestingModule({
      controllers: [TagsController],
      providers: [
        { provide: TagsService, useValue: tagsServiceMock },
        { provide: TagsDbService, useValue: tagsDbServiceMock },
      ],
    }).compile();

    controller = module.get<TagsController>(TagsController);
    tagsService = module.get(TagsService) as jest.Mocked<TagsService>;
    tagsDbService = module.get(TagsDbService) as jest.Mocked<TagsDbService>;
  });

  it('should be defined', () => {
    expect(controller).toBeDefined();
  });
});
