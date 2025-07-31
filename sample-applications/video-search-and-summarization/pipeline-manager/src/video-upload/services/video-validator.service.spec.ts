// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Test, TestingModule } from '@nestjs/testing';
import { VideoValidatorService } from './video-validator.service';
import * as childProcess from 'child_process';

// Create Jest mocks for child_process methods
jest.mock('child_process', () => ({
  execSync: jest.fn(),
  execFileSync: jest.fn(),
}));

describe('VideoValidatorService', () => {
  let service: VideoValidatorService;
  let execSyncMock: jest.MockedFunction<typeof childProcess.execSync>;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [VideoValidatorService],
    }).compile();

    service = module.get<VideoValidatorService>(VideoValidatorService);
    execSyncMock = childProcess.execSync as jest.MockedFunction<
      typeof childProcess.execSync
    >;

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
    it('should return true when file is streamable (script returns 1)', () => {
      // Mock the execSync to return a Buffer with '1'
      execSyncMock.mockReturnValue(Buffer.from('1'));

      const result = service.isStreamable('/path/to/valid/video.mp4');

      expect(result).toBe(true);
      expect(execSyncMock).toHaveBeenCalledWith(
        './lib/streamable.sh /path/to/valid/video.mp4',
      );
    });

    it('should return false when file is not streamable (script returns 0)', () => {
      // Mock the execSync to return a Buffer with '0'
      execSyncMock.mockReturnValue(Buffer.from('0'));

      const result = service.isStreamable('/path/to/non-streamable/video.mp4');

      expect(result).toBe(false);
      expect(execSyncMock).toHaveBeenCalledWith(
        './lib/streamable.sh /path/to/non-streamable/video.mp4',
      );
    });

    it('should return false when script returns any value other than 1', () => {
      // Mock the execSync to return a Buffer with something other than '1'
      execSyncMock.mockReturnValue(Buffer.from('2'));

      const result = service.isStreamable('/path/to/video.mp4');

      expect(result).toBe(false);
      expect(execSyncMock).toHaveBeenCalled();
    });

    it('should handle script output with whitespace', () => {
      // Mock the execSync to return a Buffer with '1' and whitespace
      execSyncMock.mockReturnValue(Buffer.from('1\n'));

      const result = service.isStreamable('/path/to/video.mp4');

      expect(result).toBe(true);
      expect(execSyncMock).toHaveBeenCalled();
    });

    it('should throw an error when the script execution fails', () => {
      // Mock the execSync to throw an error
      const errorMessage = 'Command failed with exit code 1';
      execSyncMock.mockImplementation(() => {
        throw new Error(errorMessage);
      });

      expect(() => {
        service.isStreamable('/path/to/invalid/video.mp4');
      }).toThrow();

      expect(execSyncMock).toHaveBeenCalled();
      expect(console.log).toHaveBeenCalled(); // Should log the error
    });

    it('should handle empty file path gracefully', () => {
      // Test behavior with empty file path
      execSyncMock.mockReturnValue(Buffer.from('0'));

      const result = service.isStreamable('');

      expect(result).toBe(false);
      expect(execSyncMock).toHaveBeenCalledWith('./lib/streamable.sh ');
    });

    it('should handle file paths with special characters', () => {
      // Test behavior with paths containing special characters
      execSyncMock.mockReturnValue(Buffer.from('1'));

      const result = service.isStreamable('/path/to/video with spaces.mp4');

      expect(result).toBe(true);
      // Verify the exact command string that would be executed
      expect(execSyncMock).toHaveBeenCalledWith(
        './lib/streamable.sh /path/to/video with spaces.mp4',
      );
    });

    it('should log the script output', () => {
      execSyncMock.mockReturnValue(Buffer.from('1'));

      service.isStreamable('/path/to/video.mp4');

      // Verify console.log was called with the script output
      expect(console.log).toHaveBeenCalledWith('1');
    });
  });
});
