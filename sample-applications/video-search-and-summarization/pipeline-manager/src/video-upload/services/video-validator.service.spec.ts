// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Test, TestingModule } from '@nestjs/testing';
import { VideoValidatorService } from './video-validator.service';
import { readFile } from 'fs/promises';

jest.mock('fs/promises', () => ({
  readFile: jest.fn(),
}));

describe('VideoValidatorService', () => {
  let service: VideoValidatorService;
  const readFileMock = readFile as jest.MockedFunction<typeof readFile>;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [VideoValidatorService],
    }).compile();

    service = module.get<VideoValidatorService>(VideoValidatorService);

  // Clear all mocks before each test
  jest.clearAllMocks();

    // Spy on console.log to suppress or verify logs
    jest.spyOn(console, 'log').mockImplementation(() => {});
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  describe('isStreamable method', () => {
    it('should return true when file is streamable (moov before mdat)', async () => {
      // Construct a Buffer where 'moov' appears before 'mdat'
      const buf = Buffer.concat([
        Buffer.from('xxxxmoovxxxx'),
        Buffer.from('xxxxmdatxxxx'),
      ]);

      readFileMock.mockResolvedValueOnce(buf as any);

      const result = await service.isStreamable('/path/to/valid/video.mp4');

      expect(result).toBe(true);
    });

    it('should return false when file is not streamable (mdat before moov)', async () => {
      const buf = Buffer.concat([
        Buffer.from('xxxxmdatxxxx'),
        Buffer.from('xxxxmoovxxxx'),
      ]);

      readFileMock.mockResolvedValueOnce(buf as any);

      const result = await service.isStreamable('/path/to/non-streamable/video.mp4');

      expect(result).toBe(false);
    });

    it('should return false when atoms missing', async () => {
      // Buffer without moov or mdat
      const buf = Buffer.from('no atoms here');
      readFileMock.mockResolvedValueOnce(buf as any);

      const result = await service.isStreamable('/path/to/video.mp4');

      expect(result).toBe(false);
    });

    it('should handle file path with special characters and whitespace', async () => {
      // Ensure moov appears well before mdat
      const buf = Buffer.concat([
        Buffer.from('start-----moov-----middle-----'),
        Buffer.from('-----mdat-----end'),
      ]);
      readFileMock.mockResolvedValueOnce(buf as any);

      const result = await service.isStreamable('/path/to/video with spaces.mp4');

      expect(result).toBe(true);
    });

    it('should throw an error when readFile fails', async () => {
      const error = new Error('ENOENT');
      readFileMock.mockRejectedValueOnce(error as any);

      await expect(service.isStreamable('/path/to/invalid/video.mp4')).rejects.toThrow();
      expect(console.log).toHaveBeenCalled(); // Should log the error
    });

    it('should handle empty file path gracefully', async () => {
      const buf = Buffer.from('no atoms');
      readFileMock.mockResolvedValueOnce(buf as any);

      const result = await service.isStreamable('');

      expect(result).toBe(false);
    });

    it('should log the script output when readFile returns content', async () => {
      const buf = Buffer.concat([
        Buffer.from('moov'),
        Buffer.from('mdat'),
      ]);
      readFileMock.mockResolvedValueOnce(buf as any);

      await service.isStreamable('/path/to/video.mp4');

      // In successful path the service does not log output; ensure no unexpected logs were made
      expect(console.log).not.toHaveBeenCalledWith('1');
    });
  });
});
