// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { HttpService } from '@nestjs/axios';
import { Injectable } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { Client } from 'minio';
import * as path from 'path';

@Injectable()
export class DatastoreService {
  baseURL: string;

  bucket: string = this.$config.get('datastore.bucketName')!;

  private client: Client;

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
    const accessKey: string = this.$config.get('datastore.accessKey')!;
    const secretKey: string = this.$config.get('datastore.secretKey')!;

    this.client = new Client({
      endPoint,
      port,
      accessKey,
      secretKey,
      useSSL: false,
    });

    const bucketExists = await this.client.bucketExists(this.bucket);

    if (!bucketExists) {
      await this.client.makeBucket(this.bucket);

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

      await this.client.setBucketPolicy(this.bucket, JSON.stringify(policy));
    }
  }

  private getExtension(fileName: string): string {
    const fileSplitted = fileName.split('.');
    return fileSplitted.pop()!;
  }

  getObjectName(
    stateId: string,
    originalFileName: string,
  ): { objectPath: string; fileExtn: string } {
    const fileName = originalFileName;
    const fileExtn = this.getExtension(originalFileName);
    return { objectPath: `${stateId}/${fileName}`, fileExtn };
  }

  getObjectURL(objectName: string): string {
    const endPoint: string = this.$config.get('datastore.host')!;
    const port: number = this.$config.get('datastore.port')!;
    const protocol: string = this.$config.get('datastore.protocol')!;
    return `${protocol}//${endPoint}:${port}${this.getObjectRelativePath(objectName)}`;
  }

  getObjectRelativePath(objectName: string): string {
    return `/${this.bucket}/${objectName}`;
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
    try {
      return this.client.fPutObject(this.bucket, destinationObject, sourceFile);
    } catch (error) {
      throw error;
    }
  }

  async getFile(objectName: string): Promise<string> {
    const filePath = path.join(__dirname, 'temp', objectName);

    const fileContent = await this.client.fGetObject(
      this.bucket,
      objectName,
      filePath,
    );

    console.log(filePath);

    return filePath;
  }
}
