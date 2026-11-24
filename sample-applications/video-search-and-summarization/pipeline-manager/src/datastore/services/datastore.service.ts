// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { HttpService } from '@nestjs/axios';
import { Injectable } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
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
import { randomUUID } from 'crypto';
import { createReadStream, createWriteStream } from 'fs';
import { mkdir, rename, rm, stat } from 'fs/promises';
import { lookup } from 'mime-types';
import * as path from 'path';
import { Readable } from 'stream';
import { pipeline } from 'stream/promises';

@Injectable()
export class DatastoreService {
  baseURL: string;

  bucket: string = this.$config.get('datastore.bucketName')!;

  private client: S3Client;

  constructor(
    private $http: HttpService,
    private $config: ConfigService,
  ) {
    this.baseURL = this.$config.get<string>('datastore.baseUrl') || '';
    this.initialize().catch((error) => {
      console.error(
        'Encountered exception while initializing Datastore service: ',
      );
      throw error;
    });
  }

  private async initialize() {
    const endPoint: string = this.$config.get('datastore.host')!;
    const port: number = this.$config.get('datastore.port')!;
    const protocol: string = this.$config.get('datastore.protocol')!;
    const accessKey: string = this.$config.get('datastore.accessKey')!;
    const secretKey: string = this.$config.get('datastore.secretKey')!;

    this.client = new S3Client({
      endpoint: `${protocol}//${endPoint}:${port}`,
      region: 'us-east-1',
      forcePathStyle: true,
      credentials: { accessKeyId: accessKey, secretAccessKey: secretKey },
    });

    try {
      await this.client.send(new HeadBucketCommand({ Bucket: this.bucket }));
    } catch (error) {
      if (!DatastoreService.isNotFoundError(error)) {
        throw error;
      }
      await this.client.send(new CreateBucketCommand({ Bucket: this.bucket }));

      const policy = {
        Version: '2012-10-17',
        Statement: [
          {
            Effect: 'Allow',
            Principal: '*',
            Action: ['s3:GetObject'],
            Resource: [`arn:aws:s3:::${this.bucket}/*`],
          },
        ],
      };

      await this.client.send(
        new PutBucketPolicyCommand({
          Bucket: this.bucket,
          Policy: JSON.stringify(policy),
        }),
      );
    }
  }

  private getExtension(fileName: string): string {
    const fileSplitted = fileName.split('.');
    return fileSplitted.pop()!;
  }

  private encodeObjectPath(objectName: string): string {
    const normalizedObjectName = objectName.replace(/^\/+/, '');
    return normalizedObjectName
      .split('/')
      .map((segment) => encodeURIComponent(segment))
      .join('/');
  }

  getObjectName(
    stateId: string,
    originalFileName: string,
  ): { objectPath: string; fileExtn: string } {
    const baseName = path.basename(originalFileName || '').trim();
    const fileExtn = this.getExtension(baseName);
    const hasFileExtension = baseName.includes('.') && !baseName.endsWith('.');
    // Use a deterministic storage key so downstream services never depend on user-supplied names.
    const storageFileName = hasFileExtension ? `source.${fileExtn}` : 'source';
    return { objectPath: `${stateId}/${storageFileName}`, fileExtn };
  }

  getObjectURL(objectName: string): string {
    const endPoint: string = this.$config.get('datastore.host')!;
    const port: number = this.$config.get('datastore.port')!;
    const protocol: string = this.$config.get('datastore.protocol')!;
    return `${protocol}//${endPoint}:${port}${this.getObjectRelativePath(objectName)}`;
  }

  getObjectRelativePath(objectName: string): string {
    return `/${this.bucket}/${this.encodeObjectPath(objectName)}`;
  }

  getWithURL(accessPath: string) {
    const endPoint: string = this.$config.get('datastore.host')!;
    const port: number = this.$config.get('datastore.port')!;
    const protocol: string = this.$config.get('datastore.protocol')!;

    if (!accessPath.startsWith('/')) {
      accessPath = `/${accessPath}`;
    }

    return `${protocol}//${endPoint}:${port}${accessPath}`;
  }

  async uploadFile(destinationObject: string, sourceFile: string) {
    const fileStat = await stat(sourceFile);
    const body = createReadStream(sourceFile);
    try {
      return await new Upload({
        client: this.client,
        params: {
          Bucket: this.bucket,
          Key: destinationObject,
          Body: body,
          ContentLength: fileStat.size,
          ContentType: lookup(sourceFile) || 'application/octet-stream',
        },
        queueSize: 1,
        partSize: Math.max(64 * 1024 * 1024, Math.ceil(fileStat.size / 10000)),
      }).done();
    } finally {
      body.destroy();
    }
  }

  async getFile(objectName: string): Promise<string> {
    const root = path.resolve(process.cwd(), 'temp');
    const filePath = path.resolve(root, objectName);
    const relative = path.relative(root, filePath);
    if (
      !relative ||
      relative.startsWith(`..${path.sep}`) ||
      relative === '..' ||
      path.isAbsolute(relative)
    ) {
      throw new Error('Invalid object path');
    }
    await mkdir(path.dirname(filePath), { recursive: true, mode: 0o700 });
    const temporaryPath = `${filePath}.${randomUUID()}.part`;
    const response = await this.client.send(
      new GetObjectCommand({ Bucket: this.bucket, Key: objectName }),
    );
    if (!(response.Body instanceof Readable)) {
      throw new Error('Object response does not contain a readable stream');
    }
    try {
      await pipeline(
        response.Body,
        createWriteStream(temporaryPath, { flags: 'wx', mode: 0o600 }),
      );
      await rename(temporaryPath, filePath);
    } finally {
      await rm(temporaryPath, { force: true });
    }
    return filePath;
  }

  /** Server-side copy within the app bucket; the bytes never leave MinIO. */
  async copyObject(sourceObject: string, destinationObject: string) {
    const source = sourceObject.replace(/^\/+/, '');
    return this.client.send(
      new CopyObjectCommand({
        Bucket: this.bucket,
        Key: destinationObject,
        CopySource: `${encodeURIComponent(this.bucket)}/${this.encodeObjectPath(source)}`,
      }),
    );
  }

  async deleteObject(objectName: string): Promise<void> {
    await this.client.send(
      new DeleteObjectCommand({ Bucket: this.bucket, Key: objectName }),
    );
  }

  static isNotFoundError(error: unknown): boolean {
    const details = error as {
      code?: string;
      name?: string;
      $metadata?: { httpStatusCode?: number };
    } | null;
    if (details?.code && details.code !== 'UnknownError') {
      return details.code === 'NotFound' || details.code === 'NoSuchKey';
    }
    if (
      details?.name &&
      details.name !== 'UnknownError' &&
      details.name !== 'Error'
    ) {
      return details.name === 'NotFound' || details.name === 'NoSuchKey';
    }
    return details?.$metadata?.httpStatusCode === 404;
  }

  async uploadBuffer(objectName: string, content: Buffer, contentType: string) {
    return this.client.send(
      new PutObjectCommand({
        Bucket: this.bucket,
        Key: objectName,
        Body: content,
        ContentLength: content.length,
        ContentType: contentType,
      }),
    );
  }

  /** Stat an object in the app bucket; `null` when it does not exist. */
  async statObject(objectName: string) {
    try {
      return await this.client.send(
        new HeadObjectCommand({ Bucket: this.bucket, Key: objectName }),
      );
    } catch (error) {
      if (DatastoreService.isNotFoundError(error)) {
        return null;
      }
      throw error;
    }
  }

  /**
   * Read an object fully into memory, aborting once it exceeds `maxBytes` so
   * a large object can never exhaust the process heap.
   */
  async getObjectBuffer(objectName: string, maxBytes: number): Promise<Buffer> {
    const { Body: stream } = await this.client.send(
      new GetObjectCommand({ Bucket: this.bucket, Key: objectName }),
    );
    if (!(stream instanceof Readable)) {
      throw new Error('Object response does not contain a readable stream');
    }
    const chunks: Buffer[] = [];
    let total = 0;
    for await (const chunk of stream) {
      const buf = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
      total += buf.length;
      if (total > maxBytes) {
        stream.destroy();
        throw new Error(
          `Object ${objectName} exceeds the maximum size of ${maxBytes} bytes`,
        );
      }
      chunks.push(buf);
    }
    return Buffer.concat(chunks);
  }
}
