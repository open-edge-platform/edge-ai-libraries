import { Test, TestingModule } from '@nestjs/testing';
import { SearchStateService } from './search-state.service';

describe('SearchStateService', () => {
  let service: SearchStateService;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [SearchStateService],
    }).compile();

    service = module.get<SearchStateService>(SearchStateService);
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });
});
