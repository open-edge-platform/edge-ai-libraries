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
import { ApiTags, ApiOperation, ApiBody, ApiParam, ApiOkResponse, ApiCreatedResponse, ApiBadRequestResponse, ApiNotFoundResponse } from '@nestjs/swagger';
import { SearchQueryDTO, SearchShimQuery, RefetchBodyDTO, WatchBodyDTO } from '../model/search.model';
import { SearchStateService } from '../services/search-state.service';
import { SearchDbService } from '../services/search-db.service';
import { SearchShimService } from '../services/search-shim.service';
import { SearchImageService } from '../services/search-image.service';
import { FeaturesService } from 'src/features/features.service';
import { lastValueFrom } from 'rxjs';

import { v4 as uuidV4 } from 'uuid';

@ApiTags('Search')
@Controller('search')
export class SearchController {
  constructor(
    private $search: SearchStateService,
    private $searchDB: SearchDbService,
    private $searchShim: SearchShimService,
    private $feature: FeaturesService,
    private $searchImage: SearchImageService,
  ) {}

  private static isNonBlank(value: unknown): value is string {
    return typeof value === 'string' && value.trim().length > 0;
  }

  /**
   * Validate that exactly one search input is given and return the query
   * image as base64/data URL, or `null` for a text search. An `imageUrl`
   * is resolved from the object store here, so everything downstream keeps
   * handling a single inline-image form.
   */
  private async resolveSearchImage(
    reqBody: SearchQueryDTO,
  ): Promise<string | null> {
    const hasImage = SearchController.isNonBlank(reqBody.image);
    const hasImageUrl = SearchController.isNonBlank(reqBody.imageUrl);
    const hasText = SearchController.isNonBlank(reqBody.query);
    if (hasImage && hasImageUrl) {
      throw new BadRequestException(
        'Provide either an image or an imageUrl, not both.',
      );
    }
    if ((hasImage || hasImageUrl) && hasText) {
      throw new BadRequestException(
        'Provide either a text query or an image, not both.',
      );
    }
    if (!hasImage && !hasImageUrl && !hasText) {
      throw new BadRequestException('Search query cannot be empty.');
    }
    if ((hasImage || hasImageUrl) && !this.$feature.isImageSearchEnabled()) {
      throw new BadRequestException(
        'Image search is not supported in this deployment mode.',
      );
    }
    if (hasImageUrl) {
      return await this.$searchImage.resolveToDataUrl(reqBody.imageUrl!);
    }
    return hasImage ? reqBody.image! : null;
  }

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
    return await this.$search.getQuery(params.queryId);
  }

  @Post('')
  @ApiOperation({ summary: 'Add a new search query' })
  @ApiBody({ type: SearchQueryDTO })
  @ApiCreatedResponse({ description: 'Search query created' })
  @ApiBadRequestResponse({ description: 'Search query is empty or invalid' })
  @ApiNotFoundResponse({ description: 'imageUrl does not refer to a stored image' })
  async addQuery(@Body() reqBody: SearchQueryDTO) {
    const image = await this.resolveSearchImage(reqBody);

    try {
      let tags: string[] = [];

      const searchQuery = reqBody.query ?? '';

      if (reqBody.tags && reqBody.tags.length > 0) {
        tags = reqBody.tags.split(',').map((tag) => tag.trim());
      }

      const query = await this.$search.newQuery(
        searchQuery,
        tags,
        reqBody.timeFilter,
        image,
      );
      return query;
    } catch (error) {
      // Preserve explicit client errors (e.g. unsupported mode / bad input).
      if (error instanceof BadRequestException) {
        throw error;
      }
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
  @ApiBadRequestResponse({ description: 'Search query is empty or invalid' })
  @ApiNotFoundResponse({ description: 'imageUrl does not refer to a stored image' })
  async searchQuery(@Body() reqBody: SearchQueryDTO) {
    const image = await this.resolveSearchImage(reqBody);

    const normalized = this.$search.buildTimeFilterRange(reqBody.timeFilter);
    const tags = reqBody.tags
      ? reqBody.tags
          .split(',')
          .map((tag) => tag.trim())
          .filter((tag) => tag.length > 0)
      : [];
    const queryShim: SearchShimQuery = {
      query_id: uuidV4(),
    };
    if (tags.length > 0) {
      queryShim.tags = tags;
    }
    if (image) {
      queryShim.image_base64 = image;
    } else {
      queryShim.query = reqBody.query;
    }
    if (normalized.range) {
      queryShim.time_filter = normalized.range;
    }
    const res = await lastValueFrom(this.$searchShim.search([queryShim]));
    const data = res.data;
    // Same join the persisted-query path applies, so a one-off search hit
    // is playable without a separate GET /videos round trip.
    for (const body of data?.results ?? []) {
      body.results = await this.$search.enrichResultsWithVideos(body.results);
    }
    return data;
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
