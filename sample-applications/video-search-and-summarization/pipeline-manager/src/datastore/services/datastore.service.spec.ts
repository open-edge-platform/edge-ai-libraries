// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Test, TestingModule } from '@nestjs/testing';
import { DatastoreService } from './datastore.service';
import { HttpService } from '@nestjs/axios';
import { ConfigService } from '@nestjs/config';
import { Client as MinioClient } from 'minio';
import * as path from 'path';

// Mock for Minio Client
jest.mock('minio', () => {
  const mockBucketExists = jest.fn();
  const mockMakeBucket = jest.fn();
  const mockSetBucketPolicy = jest.fn();
  const mockFPutObject = jest.fn();
  const mockFGetObject = jest.fn();

  return {
    Client: jest.fn().mockImplementation(() => ({
      bucketExists: mockBucketExists,
      makeBucket: mockMakeBucket,
      setBucketPolicy: mockSetBucketPolicy,
      fPutObject: mockFPutObject,
      fGetObject: mockFGetObject,
    })),
  };
});

// Mock for path.join
jest.mock('path', () => ({
  join: jest.fn().mockImplementation((...args) => args.join('/')),
}));

describe('DatastoreService', () => {
  let service: DatastoreService;
  let httpService: HttpService;
  let configService: ConfigService;
  let minioClient: any;
  let mockClientImplementation: any;

  const mockConfig = {
    'datastore.bucketName': 'test-bucket',
    'datastore.baseUrl': 'http://localhost:9000',
    'datastore.host': 'localhost',
    'datastore.port': 9000,
    'datastore.accessKey': 'minioadmin',
    'datastore.secretKey': 'minioadmin',
    'datastore.protocol': 'http:',
  };

  beforeEach(async () => {
    // Reset mocks before each test
    jest.clearAllMocks();

    // Prepare mock implementations
    mockClientImplementation = {
      bucketExists: jest.fn(),
      makeBucket: jest.fn(),
      setBucketPolicy: jest.fn(),
      fPutObject: jest.fn(),
      fGetObject: jest.fn(),
    };

    // Update the MinioClient mock implementation
    (MinioClient as jest.Mock).mockImplementation(
      () => mockClientImplementation,
    );

    // Mock implementation for ConfigService.get
    const mockConfigService = {
      get: jest.fn((key: string) => mockConfig[key]),
    };

    // Mock implementation for HttpService
    const mockHttpService = {
      // Add any HttpService methods you need to mock
    };

    // Create the test module with mocked dependencies
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        DatastoreService,
        {
          provide: HttpService,
          useValue: mockHttpService,
        },
        {
          provide: ConfigService,
          useValue: mockConfigService,
        },
      ],
    }).compile();

    httpService = module.get<HttpService>(HttpService);
    configService = module.get<ConfigService>(ConfigService);

    // Set up default mock behavior before service instantiation
    mockClientImplementation.bucketExists.mockResolvedValue(true);

    // Now create the service with the mocked behavior
    service = module.get<DatastoreService>(DatastoreService);
    minioClient = (service as any).client;
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  describe('initialization', () => {
    it('should create a bucket if it does not exist', async () => {
      // Create a new instance with bucket that doesn't exist
      mockClientImplementation.bucketExists.mockReset();
      mockClientImplementation.bucketExists.mockResolvedValueOnce(false);

      // Call initialize directly to test the bucket creation path
      await (service as any).initialize();

      expect(mockClientImplementation.bucketExists).toHaveBeenCalledWith(
        'test-bucket',
      );
      expect(mockClientImplementation.makeBucket).toHaveBeenCalledWith(
        'test-bucket',
      );
      expect(mockClientImplementation.setBucketPolicy).toHaveBeenCalledWith(
        'test-bucket',
        expect.stringContaining('"Resource":["arn:aws:s3:::test-bucket/*"]'),
      );
    });

    it('should not create a bucket if it already exists', async () => {
      // Reset counters to ensure we're only testing the specific initialize call
      mockClientImplementation.bucketExists.mockReset();
      mockClientImplementation.bucketExists.mockResolvedValueOnce(true);
      mockClientImplementation.makeBucket.mockReset();
      mockClientImplementation.setBucketPolicy.mockReset();

      // Test initialization with existing bucket
      await (service as any).initialize();

      expect(mockClientImplementation.bucketExists).toHaveBeenCalledWith(
        'test-bucket',
      );
      expect(mockClientImplementation.makeBucket).not.toHaveBeenCalled();
      expect(mockClientImplementation.setBucketPolicy).not.toHaveBeenCalled();
    });

    it('should handle bucket existence check failure', async () => {
      mockClientImplementation.bucketExists.mockReset();
      mockClientImplementation.bucketExists.mockRejectedValueOnce(
        new Error('Connection error'),
      );

      await expect((service as any).initialize()).rejects.toThrow(
        'Connection error',
      );
    });

    it('should handle bucket creation failure', async () => {
      mockClientImplementation.bucketExists.mockReset();
      mockClientImplementation.bucketExists.mockResolvedValueOnce(false);
      mockClientImplementation.makeBucket.mockReset();
      mockClientImplementation.makeBucket.mockRejectedValueOnce(
        new Error('Permission denied'),
      );

      await expect((service as any).initialize()).rejects.toThrow(
        'Permission denied',
      );
    });

    it('should handle bucket policy setting failure', async () => {
      mockClientImplementation.bucketExists.mockReset();
      mockClientImplementation.bucketExists.mockResolvedValueOnce(false);
      mockClientImplementation.makeBucket.mockReset();
      mockClientImplementation.makeBucket.mockResolvedValueOnce(undefined);
      mockClientImplementation.setBucketPolicy.mockReset();
      mockClientImplementation.setBucketPolicy.mockRejectedValueOnce(
        new Error('Policy error'),
      );

      await expect((service as any).initialize()).rejects.toThrow(
        'Policy error',
      );
    });
  });

  describe('getExtension', () => {
    it('should extract file extension correctly', () => {
      const extension = (service as any).getExtension('test-file.jpg');
      expect(extension).toBe('jpg');
    });

    it('should handle filenames with multiple dots', () => {
      const extension = (service as any).getExtension('test.file.png');
      expect(extension).toBe('png');
    });

    it('should handle filenames without extensions', () => {
      const extension = (service as any).getExtension('testfile');
      expect(extension).toBe('testfile');
    });
  });

  describe('getObjectName', () => {
    it('should generate correct object path and extension', () => {
      const result = service.getObjectName('state-123', 'sample.mp4');
      expect(result).toEqual({
        objectPath: 'state-123/sample.mp4',
        fileExtn: 'mp4',
      });
    });

    it('should handle filenames with multiple dots', () => {
      const result = service.getObjectName('state-123', 'sample.original.mp4');
      expect(result).toEqual({
        objectPath: 'state-123/sample.original.mp4',
        fileExtn: 'mp4',
      });
    });

    it('should handle filenames without extensions', () => {
      const result = service.getObjectName('state-123', 'README');
      expect(result).toEqual({
        objectPath: 'state-123/README',
        fileExtn: 'README',
      });
    });
  });

  describe('getObjectURL', () => {
    it('should return the correct URL for an object', () => {
      const url = service.getObjectURL('test-path/file.mp4');
      expect(url).toBe('http://localhost:9000/test-bucket/test-path/file.mp4');
    });

    it('should handle objects with special characters', () => {
      const url = service.getObjectURL('test path/file with spaces.mp4');
      expect(url).toBe(
        'http://localhost:9000/test-bucket/test path/file with spaces.mp4',
      );
    });
  });

  describe('getObjectRelativePath', () => {
    it('should return the correct relative path for an object', () => {
      const path = service.getObjectRelativePath('test-path/file.mp4');
      expect(path).toBe('/test-bucket/test-path/file.mp4');
    });
  });

  describe('getWithURL', () => {
    it('should return a complete URL with the given path', () => {
      const url = service.getWithURL('/test-access/path');
      expect(url).toBe('http://localhost:9000/test-access/path');
    });

    it('should handle paths without leading slash', () => {
      const url = service.getWithURL('test-access/path');
      expect(url).toBe('http://localhost:9000/test-access/path');
    });
  });

  describe('uploadFile', () => {
    it('should call fPutObject with correct parameters', async () => {
      mockClientImplementation.fPutObject.mockResolvedValueOnce('etag-123');

      const result = await service.uploadFile(
        'dest/file.mp4',
        '/source/file.mp4',
      );

      expect(mockClientImplementation.fPutObject).toHaveBeenCalledWith(
        'test-bucket',
        'dest/file.mp4',
        '/source/file.mp4',
      );
      expect(result).toBe('etag-123');
    });

    it('should propagate errors during file upload', async () => {
      mockClientImplementation.fPutObject.mockRejectedValueOnce(
        new Error('Upload failed'),
      );

      await expect(
        service.uploadFile('dest/file.mp4', '/source/file.mp4'),
      ).rejects.toThrow('Upload failed');
    });

    it('should handle network timeouts during upload', async () => {
      mockClientImplementation.fPutObject.mockRejectedValueOnce(
        new Error('Network timeout'),
      );

      await expect(
        service.uploadFile('dest/file.mp4', '/source/file.mp4'),
      ).rejects.toThrow('Network timeout');
    });
  });

  describe('getFile', () => {
    beforeEach(() => {
      // Reset path.join mock for getFile tests
      (path.join as jest.Mock).mockImplementation((...args) => args.join('/'));
    });

    it('should retrieve a file correctly', async () => {
      mockClientImplementation.fGetObject.mockResolvedValueOnce(undefined);

      const result = await service.getFile('test-object/file.mp4');

      expect(mockClientImplementation.fGetObject).toHaveBeenCalledWith(
        'test-bucket',
        'test-object/file.mp4',
        expect.stringContaining('test-object/file.mp4'),
      );
      expect(result).toEqual(expect.stringContaining('test-object/file.mp4'));
    });

    it('should handle errors during file retrieval', async () => {
      mockClientImplementation.fGetObject.mockRejectedValueOnce(
        new Error('File not found'),
      );

      await expect(service.getFile('test-object/file.mp4')).rejects.toThrow(
        'File not found',
      );
    });

    it('should handle file paths with special characters', async () => {
      mockClientImplementation.fGetObject.mockResolvedValueOnce(undefined);

      await service.getFile('test object/file with spaces.mp4');

      expect(mockClientImplementation.fGetObject).toHaveBeenCalledWith(
        'test-bucket',
        'test object/file with spaces.mp4',
        expect.stringContaining('test object/file with spaces.mp4'),
      );
    });
  });
});
