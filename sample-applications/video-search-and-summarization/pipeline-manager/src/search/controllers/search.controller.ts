// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import {
  BadRequestException,
  Body,
  Controller,
  Delete,
  Get,
  Logger,
  Param,
  Patch,
  Post,
} from '@nestjs/common';
import { SearchQueryDTO, SearchShimQuery } from '../model/search.model';
import { SearchStateService } from '../services/search-state.service';
import { SearchDbService } from '../services/search-db.service';
import { SearchShimService } from '../services/search-shim.service';
import { lastValueFrom } from 'rxjs';

import { v4 as uuidV4 } from 'uuid';

@Controller('search')
export class SearchController {
  constructor(
    private $search: SearchStateService,
    private $searchDB: SearchDbService,
    private $searchShim: SearchShimService,
  ) {}

  @Get('')
  async getQueries() {
    return await this.$searchDB.readAll();
  }

  @Get(':queryId')
  async getQuery(@Param() params: { queryId: string }) {
    return await this.$searchDB.read(params.queryId);
  }

  @Post('')
  async addQuery(@Body() reqBody: SearchQueryDTO) {
    let query = await this.$search.newQuery(reqBody.query);

    Logger.log('Query created', query);

    try {
      const queryShim: SearchShimQuery = {
        query: query.query,
        query_id: query.queryId,
      };
      const results = await lastValueFrom(this.$searchShim.search([queryShim]));

      if (results.data && results.data.results.length > 0) {
        const resultRelevant = results.data.results.find(
          (el) => el.query_id === query.queryId,
        );

        const updatedQuery = await this.$search.updateResults(
          query.queryId,
          resultRelevant || { query_id: query.queryId, results: [] },
        );

        if (updatedQuery) query = updatedQuery;
      }
    } catch (error) {
      Logger.error('Error in search shim', error);
    }

    return query;
  }

  @Post('query')
  async searchQuery(@Body() reqBody: SearchQueryDTO) {
    const queryShim: SearchShimQuery = {
      query: reqBody.query,
      query_id: uuidV4(),
    };
    const res = await lastValueFrom(this.$searchShim.search([queryShim]));
    return res.data;
  }

  @Patch(':queryId/watch')
  watchQuery(
    @Param() params: { queryId: string },
    @Body() body: { watch: boolean },
  ) {
    if (!body.hasOwnProperty('watch')) {
      throw new BadRequestException('Watch property is required');
    }

    return body.watch
      ? this.$search.addToWatch(params.queryId)
      : this.$search.removeFromWatch(params.queryId);
  }

  @Delete(':queryId')
  async deleteQuery(@Param() params: { queryId: string }) {
    return await this.$searchDB.remove(params.queryId);
  }
}
