// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Injectable } from '@nestjs/common';
import {
  AudioModelRO,
  AudioTranscriptDTO,
  AudioTranscriptionRO,
  srtText,
} from '../models/audio.model';
import { HttpService } from '@nestjs/axios';
import { ConfigService } from '@nestjs/config';
import { readFileSync, unlinkSync } from 'fs';
import * as srtParserLib from 'srt-parser-2';
import { DatastoreService } from 'src/datastore/services/datastore.service';

@Injectable()
export class AudioService {
  constructor(
    private $http: HttpService,
    private $config: ConfigService,
    private $dataStore: DatastoreService,
  ) {}

  fetchModels() {
    const host = this.$config.get<string>('audio.host')!;
    const version = this.$config.get<string>('audio.version')!;
    const apiModels = this.$config.get<string>('audio.apiModels')!;
    const api = [host, version, apiModels].join('/');

    return this.$http.get<AudioModelRO>(api);
  }

  generateTranscript(requestData: AudioTranscriptDTO) {
    const host = this.$config.get<string>('audio.host')!;
    const version = this.$config.get<string>('audio.version')!;
    const apiTranscription = this.$config.get<string>(
      'audio.apiTranscription',
    )!;

    const api = [host, version, apiTranscription].join('/');

    return this.$http.post<AudioTranscriptionRO>(api, requestData, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    });
  }

  async parseTranscript(minioObjectPath: string): Promise<srtText[]> {
    const srtParser = new srtParserLib.default();

    const filePath = await this.$dataStore.getFile(minioObjectPath);

    if (!filePath) {
      throw new Error('File not found');
    }

    const fileContent = readFileSync(filePath, 'utf-8');
    const parsedSrt = srtParser.fromSrt(fileContent);

    unlinkSync(filePath);

    return parsedSrt;
  }
}
