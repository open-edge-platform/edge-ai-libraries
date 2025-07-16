import { Test, TestingModule } from '@nestjs/testing';
import { InferenceCountService } from './inference-count.service';

describe('InferenceCountService', () => {
  let service: InferenceCountService;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [InferenceCountService],
    }).compile();

    service = module.get<InferenceCountService>(InferenceCountService);
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });
});
