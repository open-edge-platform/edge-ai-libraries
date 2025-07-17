// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Test, TestingModule } from '@nestjs/testing';
import { LocalstoreService, FrameWriteDTO } from './localstore.service';
import * as fs from 'fs';

// Mock the fs module
jest.mock('fs', () => ({
  existsSync: jest.fn(),
  mkdirSync: jest.fn(),
  writeFileSync: jest.fn(),
}));

describe('LocalstoreService', () => {
  let service: LocalstoreService;

  // Mocked fs functions
  const mockExistsSync = fs.existsSync as jest.MockedFunction<
    typeof fs.existsSync
  >;
  const mockMkdirSync = fs.mkdirSync as jest.MockedFunction<
    typeof fs.mkdirSync
  >;
  const mockWriteFileSync = fs.writeFileSync as jest.MockedFunction<
    typeof fs.writeFileSync
  >;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [LocalstoreService],
    }).compile();

    service = module.get<LocalstoreService>(LocalstoreService);

    // Reset all mocks before each test
    jest.clearAllMocks();
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  describe('writeFrameCaption', () => {
    it('should create directory and write caption to file when caption provided', () => {
      // Arrange
      const frameData: FrameWriteDTO = {
        stateId: 'test-state-123',
        chunkId: 'chunk-1',
        frameId: 'frame-1',
        caption: 'This is a test caption',
      };

      mockExistsSync.mockReturnValueOnce(false); // State dir doesn't exist

      // Act
      const result = service.writeFrameCaption(frameData);

      // Assert
      expect(mockExistsSync).toHaveBeenCalledWith('data/test-state-123');
      expect(mockMkdirSync).toHaveBeenCalledWith('data/test-state-123', {
        recursive: true,
      });
      expect(mockWriteFileSync).toHaveBeenCalledWith(
        'data/test-state-123/chunk_chunk-1_frame_frame-1.txt',
        'This is a test caption',
        { flag: 'w+' },
      );
      expect(result).toBe(
        'data/test-state-123/chunk_chunk-1_frame_frame-1.txt',
      );
    });

    it('should not create file when caption is not provided', () => {
      // Arrange
      const frameData: FrameWriteDTO = {
        stateId: 'test-state-123',
        chunkId: 'chunk-1',
        frameId: 'frame-1',
      };

      mockExistsSync.mockReturnValueOnce(false); // State dir doesn't exist

      // Act
      const result = service.writeFrameCaption(frameData);

      // Assert
      expect(mockExistsSync).toHaveBeenCalledWith('data/test-state-123');
      expect(mockMkdirSync).toHaveBeenCalledWith('data/test-state-123', {
        recursive: true,
      });
      expect(mockWriteFileSync).not.toHaveBeenCalled();
      expect(result).toBeNull();
    });

    it('should not create directory if it already exists', () => {
      // Arrange
      const frameData: FrameWriteDTO = {
        stateId: 'test-state-123',
        chunkId: 'chunk-1',
        frameId: 'frame-1',
        caption: 'Test caption',
      };

      mockExistsSync.mockReturnValueOnce(true); // State dir exists

      // Act
      service.writeFrameCaption(frameData);

      // Assert
      expect(mockExistsSync).toHaveBeenCalledWith('data/test-state-123');
      expect(mockMkdirSync).not.toHaveBeenCalled();
      expect(mockWriteFileSync).toHaveBeenCalled();
    });
  });

  describe('private methods via testing public methods', () => {
    it('should construct correct frame path', () => {
      // Arrange
      const frameData: FrameWriteDTO = {
        stateId: 'state-abc',
        chunkId: 'chunk-xyz',
        frameId: 'frame-123',
        caption: 'Test caption',
      };

      mockExistsSync.mockReturnValueOnce(true); // State dir exists

      // Act
      service.writeFrameCaption(frameData);

      // Assert - checking if the writeFileSync was called with correct path
      expect(mockWriteFileSync).toHaveBeenCalledWith(
        'data/state-abc/chunk_chunk-xyz_frame_frame-123.txt',
        'Test caption',
        expect.anything(),
      );
    });

    it('should handle special characters in IDs correctly', () => {
      // Arrange
      const frameData: FrameWriteDTO = {
        stateId: 'state/with/slashes',
        chunkId: 'chunk.with.dots',
        frameId: 'frame-with-spaces and_symbols',
        caption: 'Test special characters',
      };

      mockExistsSync.mockReturnValueOnce(false); // State dir doesn't exist

      // Act
      service.writeFrameCaption(frameData);

      // Assert
      expect(mockExistsSync).toHaveBeenCalledWith('data/state/with/slashes');
      expect(mockWriteFileSync).toHaveBeenCalledWith(
        'data/state/with/slashes/chunk_chunk.with.dots_frame_frame-with-spaces and_symbols.txt',
        'Test special characters',
        expect.anything(),
      );
    });
  });

  describe('edge cases', () => {
    it('should handle empty stateId', () => {
      // Arrange
      const frameData: FrameWriteDTO = {
        stateId: '',
        chunkId: 'chunk-1',
        frameId: 'frame-1',
        caption: 'Caption with empty stateId',
      };

      mockExistsSync.mockReturnValueOnce(false); // State dir doesn't exist

      // Act & Assert
      expect(() => {
        service.writeFrameCaption(frameData);
      }).not.toThrow();

      expect(mockExistsSync).toHaveBeenCalledWith('data/');
      expect(mockWriteFileSync).toHaveBeenCalled();
    });

    it('should handle file system errors', () => {
      // Arrange
      const frameData: FrameWriteDTO = {
        stateId: 'error-state',
        chunkId: 'chunk-1',
        frameId: 'frame-1',
        caption: 'Caption',
      };

      mockExistsSync.mockReturnValueOnce(false);
      mockMkdirSync.mockImplementationOnce(() => {
        throw new Error('Permission denied');
      });

      // Act & Assert
      expect(() => {
        service.writeFrameCaption(frameData);
      }).toThrow('Permission denied');
    });

    it('should handle very long caption text', () => {
      // Arrange
      const longCaption = 'A'.repeat(10000); // 10KB string
      const frameData: FrameWriteDTO = {
        stateId: 'test-state',
        chunkId: 'chunk-1',
        frameId: 'frame-1',
        caption: longCaption,
      };

      mockExistsSync.mockReturnValueOnce(true); // State dir exists

      // Act
      const result = service.writeFrameCaption(frameData);

      // Assert
      expect(mockWriteFileSync).toHaveBeenCalledWith(
        expect.any(String),
        longCaption,
        expect.anything(),
      );
      expect(result).toBe('data/test-state/chunk_chunk-1_frame_frame-1.txt');
    });
  });

  describe('custom data path', () => {
    it('should use custom data path when set', () => {
      // Arrange
      service.dataPath = 'custom/data/path';

      const frameData: FrameWriteDTO = {
        stateId: 'test-state',
        chunkId: 'chunk-1',
        frameId: 'frame-1',
        caption: 'Caption with custom path',
      };

      mockExistsSync.mockReturnValueOnce(false); // Custom state dir doesn't exist

      // Act
      service.writeFrameCaption(frameData);

      // Assert
      expect(mockExistsSync).toHaveBeenCalledWith(
        'custom/data/path/test-state',
      );
      expect(mockMkdirSync).toHaveBeenCalledWith(
        'custom/data/path/test-state',
        { recursive: true },
      );
      expect(mockWriteFileSync).toHaveBeenCalledWith(
        'custom/data/path/test-state/chunk_chunk-1_frame_frame-1.txt',
        'Caption with custom path',
        expect.anything(),
      );
    });
  });
});
