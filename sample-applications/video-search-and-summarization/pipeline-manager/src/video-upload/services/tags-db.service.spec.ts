import { Test, TestingModule } from '@nestjs/testing';
import { TagsDbService } from './tags-db.service';

describe('TagsDbService', () => {
  let service: TagsDbService;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [TagsDbService],
    }).compile();

    service = module.get<TagsDbService>(TagsDbService);
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });
});
