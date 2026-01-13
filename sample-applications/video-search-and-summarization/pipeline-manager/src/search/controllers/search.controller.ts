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
    return await this.$search.getQueries();
  }

  @Get('watched')
  async getWatchedQueries() {
    return await this.$searchDB.readAllWatched();
  }

  @Get(':queryId')
  async getQuery(@Param() params: { queryId: string }) {
    return await this.$searchDB.read(params.queryId);
  }

  @Post('')
  async addQuery(@Body() reqBody: SearchQueryDTO) {
    try {
      let tags: string[] = [];

      const searchQuery = reqBody.query;

      if (reqBody.tags && reqBody.tags.length > 0) {
        tags = reqBody.tags.split(',').map((tag) => tag.trim());
      }

      const query = await this.$search.newQuery(searchQuery, tags, reqBody.timeFilter);
      return query;
    } catch (error) {
      Logger.error('Error adding query', error);
      throw new BadRequestException('Error adding query');
    }
  }

  @Post(':queryId/refetch')
  async refetchQuery(@Param() params: { queryId: string }, @Body() body?: { timeFilter?: SearchQueryDTO['timeFilter'] }) {
    const res = await this.$search.reRunQuery(params.queryId, body?.timeFilter);
    return res;
  }

  @Post('query')
  async searchQuery(@Body() reqBody: SearchQueryDTO) {
    const normalized = this.$search.buildTimeFilterRange(reqBody.timeFilter);
    const queryShim: SearchShimQuery = {
      query: reqBody.query,
      query_id: uuidV4(),
    };
    if (normalized.range) {
      queryShim.time_filter = normalized.range;
    }
    const res = await lastValueFrom(this.$searchShim.search([queryShim]));
    return res.data;
  }

  @Patch(':queryId/watch')
  watchQuery(
    @Param() params: { queryId: string },
    @Body() body: { watch: boolean },
  ) {
    if (!Object.prototype.hasOwnProperty.call(body, 'watch')) {
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
