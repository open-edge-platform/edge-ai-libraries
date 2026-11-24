// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import {
  CopyObjectCommand,
  CreateBucketCommand,
  DeleteObjectCommand,
  GetObjectCommand,
  HeadBucketCommand,
  HeadObjectCommand,
  PutBucketPolicyCommand,
  PutObjectCommand,
  S3Client,
} from '@aws-sdk/client-s3';
import { Upload } from '@aws-sdk/lib-storage';
import { HttpService } from '@nestjs/axios';
import { ConfigService } from '@nestjs/config';
import { randomUUID } from 'crypto';
import { mkdir, mkdtemp, readFile, readdir, rm, writeFile } from 'fs/promises';
import { tmpdir } from 'os';
import * as path from 'path';
import { Readable } from 'stream';
import { DatastoreService } from './datastore.service';

const mockSend = jest.fn();
const mockUploadDone = jest.fn();

jest.mock('@aws-sdk/client-s3', () => ({
  ...jest.requireActual('@aws-sdk/client-s3'),
  S3Client: jest.fn().mockImplementation(() => ({ send: mockSend })),
}));

jest.mock('@aws-sdk/lib-storage', () => ({
  Upload: jest.fn().mockImplementation(() => ({ done: mockUploadDone })),
}));

describe('DatastoreService', () => {
  let service: DatastoreService;
  const config = {
    'datastore.bucketName': 'test-bucket',
    'datastore.baseUrl': 'http://localhost:9000',
    'datastore.host': 'localhost',
    'datastore.port': 9000,
    'datastore.accessKey': '<access-key>',
    'datastore.secretKey': '<secret-key>',
    'datastore.protocol': 'http:',
  };

  beforeEach(() => {
    jest.clearAllMocks();
    mockSend.mockReset().mockResolvedValue({});
    mockUploadDone.mockReset().mockResolvedValue({ ETag: 'etag' });
    const configService = {
      get: (key: string) => config[key],
    } as ConfigService;
    service = new DatastoreService({} as HttpService, configService);
  });

  describe('initialization', () => {
    it('uses the existing MinIO endpoint and path-style S3 requests', () => {
      expect(S3Client).toHaveBeenCalledWith({
        endpoint: 'http://localhost:9000',
        region: 'us-east-1',
        forcePathStyle: true,
        credentials: {
          accessKeyId: '<access-key>',
          secretAccessKey: '<secret-key>',
        },
      });
      expect(mockSend).toHaveBeenCalledWith(
        expect.objectContaining({ input: { Bucket: 'test-bucket' } }),
      );
      expect(mockSend.mock.calls[0][0]).toBeInstanceOf(HeadBucketCommand);
    });

    it('creates a missing bucket and applies the existing read policy', async () => {
      mockSend
        .mockReset()
        .mockRejectedValueOnce({ $metadata: { httpStatusCode: 404 } })
        .mockResolvedValueOnce({})
        .mockResolvedValueOnce({});

      await service['initialize']();

      expect(mockSend.mock.calls[1][0]).toBeInstanceOf(CreateBucketCommand);
      expect(mockSend.mock.calls[2][0]).toBeInstanceOf(PutBucketPolicyCommand);
      expect(JSON.parse(mockSend.mock.calls[2][0].input.Policy)).toEqual({
        Version: '2012-10-17',
        Statement: [
          {
            Effect: 'Allow',
            Principal: '*',
            Action: ['s3:GetObject'],
            Resource: ['arn:aws:s3:::test-bucket/*'],
          },
        ],
      });
    });

    it('does not create a bucket on authorization or network errors', async () => {
      const error = {
        name: 'AccessDenied',
        $metadata: { httpStatusCode: 403 },
      };
      mockSend.mockReset().mockRejectedValueOnce(error);
      await expect(service['initialize']()).rejects.toEqual(error);
      expect(mockSend).toHaveBeenCalledTimes(1);
    });

    it('propagates bucket creation and policy errors', async () => {
      mockSend
        .mockReset()
        .mockRejectedValueOnce({ name: 'NotFound' })
        .mockRejectedValueOnce(new Error('Creation error'));
      await expect(service['initialize']()).rejects.toThrow('Creation error');

      mockSend
        .mockReset()
        .mockRejectedValueOnce({ name: 'NotFound' })
        .mockResolvedValueOnce({})
        .mockRejectedValueOnce(new Error('Policy error'));
      await expect(service['initialize']()).rejects.toThrow('Policy error');
    });
  });

  describe('object paths', () => {
    it.each([
      ['sample.mp4', 'source.mp4', 'mp4'],
      ['sample.original.mp4', 'source.mp4', 'mp4'],
      ['README', 'source', 'README'],
      ['../../nested/my clip.mp4', 'source.mp4', 'mp4'],
    ])('creates deterministic keys for %s', (filename, stored, extension) => {
      expect(service.getObjectName('state-123', filename)).toEqual({
        objectPath: `state-123/${stored}`,
        fileExtn: extension,
      });
    });

    it('preserves URL paths and encodes object segments', () => {
      expect(service.getObjectURL('test path/file #1.mp4')).toBe(
        'http://localhost:9000/test-bucket/test%20path/file%20%231.mp4',
      );
      expect(service.getObjectRelativePath('/test-path/file.mp4')).toBe(
        '/test-bucket/test-path/file.mp4',
      );
      expect(service.getWithURL('test-access/path')).toBe(
        'http://localhost:9000/test-access/path',
      );
    });
  });

  describe('uploadFile', () => {
    let directory: string;

    beforeEach(async () => {
      directory = await mkdtemp(path.join(tmpdir(), 'vss-datastore-'));
    });

    afterEach(async () => {
      await rm(directory, { recursive: true, force: true });
    });

    it('streams a file with its length and inferred content type', async () => {
      const file = path.join(directory, 'video.mp4');
      await writeFile(file, 'abc');

      await expect(service.uploadFile('id/source.mp4', file)).resolves.toEqual({
        ETag: 'etag',
      });

      expect(Upload).toHaveBeenCalledWith(
        expect.objectContaining({
          client: expect.any(Object),
          params: expect.objectContaining({
            Bucket: 'test-bucket',
            Key: 'id/source.mp4',
            ContentLength: 3,
            ContentType: 'video/mp4',
            Body: expect.any(Readable),
          }),
          partSize: 64 * 1024 * 1024,
          queueSize: 1,
        }),
      );
    });

    it('uses the existing binary default and propagates upload errors', async () => {
      const file = path.join(directory, 'no-extension');
      await writeFile(file, 'abc');
      mockUploadDone.mockRejectedValueOnce(new Error('Upload failed'));

      await expect(service.uploadFile('id/source', file)).rejects.toThrow(
        'Upload failed',
      );
      expect(jest.mocked(Upload).mock.calls[0][0].params.ContentType).toBe(
        'application/octet-stream',
      );
    });
  });

  describe('getFile', () => {
    let directory: string;
    let objectDir: string;
    let cwd: jest.SpyInstance;

    beforeEach(async () => {
      directory = await mkdtemp(path.join(tmpdir(), 'vss-download-'));
      cwd = jest.spyOn(process, 'cwd').mockReturnValue(directory);
      objectDir = `test-${randomUUID()}`;
    });

    afterEach(async () => {
      cwd.mockRestore();
      await rm(directory, { recursive: true, force: true });
    });

    it('writes the response to a local file', async () => {
      const objectName = `${objectDir}/file.mp4`;
      mockSend.mockResolvedValueOnce({
        Body: Readable.from([Buffer.from('video')]),
      });
      const file = await service.getFile(objectName);
      expect(await readFile(file, 'utf8')).toBe('video');
      expect(mockSend.mock.lastCall?.[0]).toBeInstanceOf(GetObjectCommand);
    });

    it('rejects object paths outside its download directory', async () => {
      await expect(service.getFile('../outside')).rejects.toThrow(
        'Invalid object path',
      );
    });

    it('propagates failed downloads', async () => {
      mockSend.mockRejectedValueOnce(new Error('Download failed'));
      await expect(service.getFile(`${objectDir}/file`)).rejects.toThrow(
        'Download failed',
      );
    });

    it('removes partial downloads without overwriting an existing file', async () => {
      const objectName = `${objectDir}/file`;
      const destination = path.join(directory, 'temp', objectName);
      await mkdir(path.dirname(destination), { recursive: true });
      await writeFile(destination, 'existing');
      const body = Readable.from(
        (async function* () {
          yield Buffer.from('partial');
          throw new Error('Stream failed');
        })(),
      );
      mockSend.mockResolvedValueOnce({ Body: body });

      await expect(service.getFile(objectName)).rejects.toThrow(
        'Stream failed',
      );
      expect(await readFile(destination, 'utf8')).toBe('existing');
      expect(await readdir(path.dirname(destination))).toEqual(['file']);
    });
  });

  it('copies encoded keys within the bucket', async () => {
    await service.copyObject('/src id/file #1.mp4', 'dst/source.mp4');
    const command = mockSend.mock.lastCall?.[0];
    expect(command).toBeInstanceOf(CopyObjectCommand);
    expect(command.input).toEqual({
      Bucket: 'test-bucket',
      Key: 'dst/source.mp4',
      CopySource: 'test-bucket/src%20id/file%20%231.mp4',
    });
  });

  it('propagates copy errors', async () => {
    mockSend.mockRejectedValueOnce(new Error('Copy failed'));
    await expect(service.copyObject('source', 'destination')).rejects.toThrow(
      'Copy failed',
    );
  });

  it('deletes an object', async () => {
    await service.deleteObject('id/source.mp4');
    const command = mockSend.mock.lastCall?.[0];
    expect(command).toBeInstanceOf(DeleteObjectCommand);
    expect(command.input).toEqual({
      Bucket: 'test-bucket',
      Key: 'id/source.mp4',
    });
  });

  it('uploads a buffer with its content type', async () => {
    const content = Buffer.from('abc');
    await service.uploadBuffer('search-images/a.png', content, 'image/png');
    const command = mockSend.mock.lastCall?.[0];
    expect(command).toBeInstanceOf(PutObjectCommand);
    expect(command.input).toEqual({
      Bucket: 'test-bucket',
      Key: 'search-images/a.png',
      Body: content,
      ContentLength: 3,
      ContentType: 'image/png',
    });
  });

  it('maps missing objects to null and propagates other stat errors', async () => {
    mockSend.mockRejectedValueOnce({
      name: 'NotFound',
      $metadata: { httpStatusCode: 404 },
    });
    await expect(service.statObject('missing')).resolves.toBeNull();
    expect(mockSend.mock.lastCall?.[0]).toBeInstanceOf(HeadObjectCommand);
    mockSend.mockRejectedValueOnce(new Error('down'));
    await expect(service.statObject('x')).rejects.toThrow('down');
  });

  it('recognizes AWS and legacy missing-object errors', () => {
    expect(DatastoreService.isNotFoundError({ name: 'NoSuchKey' })).toBe(true);
    expect(DatastoreService.isNotFoundError({ code: 'NotFound' })).toBe(true);
    expect(
      DatastoreService.isNotFoundError({ $metadata: { httpStatusCode: 404 } }),
    ).toBe(true);
    expect(
      DatastoreService.isNotFoundError({
        name: 'NoSuchBucket',
        $metadata: { httpStatusCode: 404 },
      }),
    ).toBe(false);
    expect(DatastoreService.isNotFoundError({ name: 'AccessDenied' })).toBe(
      false,
    );
  });

  it('reads object streams and rejects oversized content', async () => {
    mockSend.mockResolvedValueOnce({ Body: Readable.from(['ab', 'cd']) });
    await expect(service.getObjectBuffer('obj', 4)).resolves.toEqual(
      Buffer.from('abcd'),
    );
    const stream = Readable.from(['abc', 'def']);
    mockSend.mockResolvedValueOnce({ Body: stream });
    await expect(service.getObjectBuffer('obj', 4)).rejects.toThrow(
      'exceeds the maximum size',
    );
    expect(stream.destroyed).toBe(true);
  });
});
