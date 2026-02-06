// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { HttpService } from '@nestjs/axios';
import { Injectable } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { tap } from 'rxjs';
import { SearchEvents } from 'src/events/Pipeline.events';
import {
  DataPrepMinioDTO,
  DataPrepMinioRO,
  DataPrepSummaryDTO,
} from '../models/data-prep.models';

@Injectable()
export class DataPrepShimService {
  constructor(
    private $config: ConfigService,
    private $http: HttpService,
    private $emitter: EventEmitter2,
  ) {}

  createEmbeddings(data: DataPrepMinioDTO) {
    const dataPrepEndpoint: string =
      this.$config.get<string>('search.dataPrep')!;
    const api = [dataPrepEndpoint, 'videos', 'minio'].join('/');
    const timeout =
      this.$config.get<number>('search.dataPrepTimeoutMs') ?? 30000;
    return this.$http.post<DataPrepMinioRO>(api, data, { timeout }).pipe(
      tap(() => {
        this.$emitter.emit(SearchEvents.EMBEDDINGS_UPDATE);
      }),
    );
  }

  createEmbeddingsFromSummary(data: DataPrepSummaryDTO) {
    const dataPrepEndpoint: string =
      this.$config.get<string>('search.dataPrep')!;
    const api = [dataPrepEndpoint, 'summary'].join('/');
    const timeout =
      this.$config.get<number>('search.dataPrepTimeoutMs') ?? 30000;

    return this.$http.post<DataPrepMinioRO>(api, data, { timeout }).pipe(
      tap(() => {
        this.$emitter.emit(SearchEvents.EMBEDDINGS_UPDATE);
      }),
    );
  }
}
