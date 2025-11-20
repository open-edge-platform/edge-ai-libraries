// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Injectable } from '@nestjs/common';
import { SearchResultRO, SearchShimQuery } from '../model/search.model';
import { ConfigService } from '@nestjs/config';
import { HttpService } from '@nestjs/axios';

@Injectable()
export class SearchShimService {
  lastEmbeddingsUpdate: number = new Date().getTime();

  constructor(
    private $config: ConfigService,
    private $http: HttpService,
  ) {}

  search(query: SearchShimQuery[]) {
    const endPoint: string = this.$config.get('search.endpoint')!;
    const api = [endPoint, 'query'].join('/') + '/';

    console.log('=== SEARCH SHIM SERVICE ===');
    console.log('api endpoint:', api);
    console.log('query payload:', JSON.stringify(query, null, 2));

    return this.$http.post<SearchResultRO>(api, query);
  }

  embeddingsUpdate() {}
}
