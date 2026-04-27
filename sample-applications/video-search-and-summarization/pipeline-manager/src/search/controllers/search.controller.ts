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
import { ApiTags, ApiOperation, ApiBody, ApiParam, ApiOkResponse, ApiCreatedResponse } from '@nestjs/swagger';
import { SearchQueryDTO, SearchShimQuery, RefetchBodyDTO, WatchBodyDTO } from '../model/search.model';
import { SearchStateService } from '../services/search-state.service';
import { SearchDbService } from '../services/search-db.service';
import { SearchShimService } from '../services/search-shim.service';
import { lastValueFrom } from 'rxjs';

import { v4 as uuidV4 } from 'uuid';

@ApiTags('Search')
@Controller('search')
export class SearchController {
  constructor(
    private $search: SearchStateService,
    private $searchDB: SearchDbService,
    private $searchShim: SearchShimService,
  ) {}

  @Get('')
  @ApiOperation({ summary: 'Get all search queries' })
  @ApiOkResponse({ description: 'Returns a list of all search queries' })
  async getQueries() {
    return await this.$search.getQueries();
  }

  @Get('watched')
  @ApiOperation({ summary: 'Get all watched search queries' })
  @ApiOkResponse({ description: 'Returns a list of watched queries' })
  async getWatchedQueries() {
    return await this.$searchDB.readAllWatched();
  }

  @Get(':queryId')
  @ApiOperation({ summary: 'Get a search query by ID' })
  @ApiParam({ name: 'queryId', type: String, description: 'ID of the search query' })
  @ApiOkResponse({ description: 'Search query details' })
  async getQuery(@Param() params: { queryId: string }) {
    return await this.$searchDB.read(params.queryId);
  }

  @Post('')
  @ApiOperation({ summary: 'Add a new search query' })
  @ApiBody({ type: SearchQueryDTO })
  @ApiCreatedResponse({ description: 'Search query created' })
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
  @ApiOperation({ summary: 'Refetch search results for a query' })
  @ApiParam({ name: 'queryId', type: String, description: 'ID of the search query to refetch' })
  @ApiBody({ type: RefetchBodyDTO, required: false })
  @ApiOkResponse({ description: 'Search query refetched' })
  async refetchQuery(@Param() params: { queryId: string }, @Body() body?: RefetchBodyDTO) {
    const res = await this.$search.reRunQuery(params.queryId, body?.timeFilter);
    return res;
  }

  @Post('query')
  @ApiOperation({ summary: 'Execute a one-off search query' })
  @ApiBody({ type: SearchQueryDTO })
  @ApiCreatedResponse({ description: 'Search results' })
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
  @ApiOperation({ summary: 'Toggle watch status for a search query' })
  @ApiParam({ name: 'queryId', type: String, description: 'ID of the search query' })
  @ApiBody({ type: WatchBodyDTO })
  @ApiOkResponse({ description: 'Watch status updated' })
  watchQuery(
    @Param() params: { queryId: string },
    @Body() body: WatchBodyDTO,
  ) {
    if (!Object.prototype.hasOwnProperty.call(body, 'watch')) {
      throw new BadRequestException('Watch property is required');
    }

    return body.watch
      ? this.$search.addToWatch(params.queryId)
      : this.$search.removeFromWatch(params.queryId);
  }

  @Delete(':queryId')
  @ApiOperation({ summary: 'Delete a search query' })
  @ApiParam({ name: 'queryId', type: String, description: 'ID of the search query to delete' })
  @ApiOkResponse({ description: 'Search query deleted' })
  async deleteQuery(@Param() params: { queryId: string }) {
    return await this.$searchDB.remove(params.queryId);
  }
}
