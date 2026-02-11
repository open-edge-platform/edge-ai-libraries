// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Injectable, Logger } from '@nestjs/common';
import {
  SearchQuery,
  SearchQueryStatus,
  SearchResultBody,
  SearchShimQuery,
  TimeFilterSelection,
  TimeFilterUnit,
} from '../model/search.model';
import { SearchEntity } from '../model/search.entity';
import { SearchDbService } from './search-db.service';
import { EventEmitter2, OnEvent } from '@nestjs/event-emitter';
import { SocketEvent } from 'src/events/socket.events';
import { SearchEvents } from 'src/events/Pipeline.events';
import { SearchShimService } from './search-shim.service';
import { lastValueFrom } from 'rxjs';
import { v4 as uuidV4 } from 'uuid';
import { VideoService } from 'src/video-upload/services/video.service';
import { VideoEntity } from 'src/video-upload/models/video.entity';

@Injectable()
export class SearchStateService {
  constructor(
    private $searchDB: SearchDbService,
    private $video: VideoService,
    private $emitter: EventEmitter2,
    private $searchShim: SearchShimService,
  ) {}

  private normalizeTimeFilter(timeFilter?: TimeFilterSelection | null): {
    selection: TimeFilterSelection | null;
    range: { start: string; end: string } | null;
  } {
    if (
      !timeFilter ||
      timeFilter.value === undefined ||
      timeFilter.value === null ||
      !timeFilter.unit
    ) {
      return { selection: null, range: null };
    }

    const value = Number(timeFilter.value);
    if (Number.isNaN(value) || value <= 0) {
      return { selection: null, range: null };
    }

    const now = new Date();
    const start = new Date(now);
    const unit = timeFilter.unit;
    switch (unit) {
      case 'minutes':
        start.setMinutes(start.getMinutes() - value);
        break;
      case 'hours':
        start.setHours(start.getHours() - value);
        break;
      case 'days':
        start.setDate(start.getDate() - value);
        break;
      case 'weeks':
        start.setDate(start.getDate() - value * 7);
        break;
      default:
        return { selection: null, range: null };
    }

    const startIso = start.toISOString();
    const endIso = now.toISOString();

    return {
      selection: {
        ...timeFilter,
        value,
        unit,
        start: startIso,
        end: endIso,
        source: timeFilter.source || 'relative',
      },
      range: { start: startIso, end: endIso },
    };
  }

  buildTimeFilterRange(timeFilter?: TimeFilterSelection | null) {
    return this.normalizeTimeFilter(timeFilter);
  }

  private buildTimeFilterFromEntity(
    entity: SearchEntity,
  ): TimeFilterSelection | null {
    const hasRange = entity.timeFilterStart || entity.timeFilterEnd;
    const hasSelection =
      entity.timeFilterValue !== null &&
      entity.timeFilterValue !== undefined &&
      !!entity.timeFilterUnit;

    if (!hasRange && !hasSelection) {
      return null;
    }

    return {
      value: entity.timeFilterValue ?? undefined,
      unit: (entity.timeFilterUnit as TimeFilterUnit) ?? undefined,
      start: entity.timeFilterStart ?? undefined,
      end: entity.timeFilterEnd ?? undefined,
      source: hasRange ? 'relative' : undefined,
    };
  }

  private toSearchQuery(entity: SearchEntity): SearchQuery {
    const timeFilter = this.buildTimeFilterFromEntity(entity);
    const {
      timeFilterValue,
      timeFilterUnit,
      timeFilterStart,
      timeFilterEnd,
      ...rest
    } = entity as any;

    return {
      ...(rest as SearchQuery),
      timeFilter,
    };
  }

  async getQueries() {
    const queries = await this.$searchDB.readAll();

    // Enrich each query with video information
    const enrichedQueries = await Promise.all(
      queries.map((query) => this.enrichQueryWithVideos(query)),
    );

    return enrichedQueries.filter((query) => query !== null);
  }

  async newQuery(
    query: string,
    tags: string[] = [],
    timeFilter?: TimeFilterSelection | null,
  ) {
    const normalized = this.normalizeTimeFilter(timeFilter);
    const searchQuery: SearchQuery = {
      queryId: uuidV4(),
      query,
      watch: false,
      results: [],
      tags,
      timeFilter: normalized.selection,
      queryStatus: SearchQueryStatus.RUNNING,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };

    Logger.log('Search Query', searchQuery);

    const res = await this.$searchDB.create(searchQuery);

    Logger.log(`Emitting RUN_QUERY for ${res.queryId} (new query)`);
    this.$emitter.emit(SearchEvents.RUN_QUERY, res.queryId);

    const enriched = await this.enrichQueryWithVideos(res);
    return enriched ?? res;
  }

  private async enrichQueryWithVideos(
    query: SearchEntity | null,
  ): Promise<SearchQuery | null> {
    if (!query) {
      return null;
    }

    const videos = await this.$video.getVideos();
    const videosKeyedById = videos.reduce(
      (acc, video) => {
        acc[video.videoId] = video;
        return acc;
      },
      {} as Record<string, VideoEntity>,
    );

    if (query.results && query.results.length > 0) {
      query.results = query.results.map((result) => {
        const video = videosKeyedById[result.metadata.video_id];
        if (video) {
          result.video = video;
        }
        return result;
      });
    }

    return this.toSearchQuery(query);
  }

  async addToWatch(queryId: string) {
    await this.$searchDB.updateWatch(queryId, true);
  }

  async removeFromWatch(queryId: string) {
    await this.$searchDB.updateWatch(queryId, false);
  }

  @OnEvent(SearchEvents.RUN_QUERY)
  async reRunQuery(queryId: string, timeFilter?: TimeFilterSelection | null) {
    const query = await this.$searchDB.read(queryId);
    if (!query) {
      throw new Error(`Query with ID ${queryId} not found`);
    }

    if (timeFilter !== undefined) {
      const normalized = this.normalizeTimeFilter(timeFilter);
      await this.$searchDB.update(queryId, {
        timeFilter: normalized.selection,
      });
      query.timeFilterValue = normalized.selection?.value ?? null;
      query.timeFilterUnit = normalized.selection?.unit ?? null;
      query.timeFilterStart = normalized.selection?.start ?? null;
      query.timeFilterEnd = normalized.selection?.end ?? null;
    }

    const updatedQuery = await this.$searchDB.updateQueryStatus(
      queryId,
      SearchQueryStatus.RUNNING,
    );
    const enrichedQuery = await this.enrichQueryWithVideos(updatedQuery);
    this.$emitter.emit(SocketEvent.SEARCH_UPDATE, enrichedQuery);

    try {
      console.log('=== RUNNING SEARCH ===');
      console.log(
        `Query ID: ${queryId}, Query: ${query}, Tags: ${JSON.stringify(query.tags)}`,
      );

      Logger.log(
        `Triggering runSearch for ${queryId} tags=${JSON.stringify(query.tags)} timeFilterStart=${query.timeFilterStart} timeFilterEnd=${query.timeFilterEnd}`,
      );

      const results = await this.runSearch(
        queryId,
        query.query,
        query.tags,
        query.timeFilterStart,
        query.timeFilterEnd,
      );

      console.log('=== SEARCH RESULTS PROCESSING ===');
      console.log('Results structure:', JSON.stringify(results, null, 2));
      console.log('Results.results length:', results.results?.length || 0);

      if (results.results.length > 0) {
        const relevantResults = results.results.find(
          (el) => el.query_id === queryId,
        );

        console.log('=== RELEVANT RESULTS CHECK ===');
        console.log('Looking for query_id:', queryId);
        console.log('Found relevant results:', !!relevantResults);
        if (relevantResults) {
          console.log(
            'Relevant results count:',
            relevantResults.results?.length || 0,
          );
        } else {
          console.log(
            'Available query_ids in results:',
            results.results.map((r) => r.query_id),
          );
        }

        if (relevantResults) {
          console.log('=== UPDATING RESULTS ===');
          const freshEntity = await this.updateResults(
            queryId,
            relevantResults,
          );
          console.log(
            'Fresh entity after update:',
            JSON.stringify(freshEntity, null, 2),
          );
          return freshEntity;
        }
        console.log('=== NO RELEVANT RESULTS FOUND ===');
        return null;
      } else {
        console.log('=== NO RESULTS FROM SEARCH API ===');
        Logger.warn(`No results found for query ID ${queryId}`);
        return null;
      }
    } catch (error) {
      console.log('=== SEARCH ERROR ===');
      console.log('Error details:', error);
      Logger.error(`Error running search for query ID ${queryId}`, error);
      const errorMessage =
        'No videos found in search database. Please upload relevant videos before running queries.';
      const updatedQuery = await this.$searchDB.updateQueryStatusWithError(
        queryId,
        SearchQueryStatus.ERROR,
        errorMessage,
      );
      console.log(
        'Updated query with error:',
        JSON.stringify(updatedQuery, null, 2),
      );
      const enrichedQuery = await this.enrichQueryWithVideos(updatedQuery);
      this.$emitter.emit(SocketEvent.SEARCH_UPDATE, enrichedQuery);
      return null;
    }
  }

  async runSearch(
    queryId: string,
    query: string,
    tags: string[],
    timeFilterStart?: string | null,
    timeFilterEnd?: string | null,
  ) {
    const queryShim: SearchShimQuery = {
      query,
      query_id: queryId,
      tags,
    };

    if (timeFilterStart && timeFilterEnd) {
      queryShim.time_filter = { start: timeFilterStart, end: timeFilterEnd };
    }

    console.log('=== SEARCH STATE SERVICE ===');
    console.log(
      'Running search with payload:',
      JSON.stringify([queryShim], null, 2),
    );

    const results = await lastValueFrom(this.$searchShim.search([queryShim]));

    console.log('=== SEARCH API RESPONSE ===');
    console.log('Raw response:', JSON.stringify(results.data, null, 2));

    return results.data || { results: [] };
  }

  async updateResults(queryId: string, results: SearchResultBody) {
    console.log('=== UPDATE RESULTS METHOD ===');
    console.log('Query ID:', queryId);
    console.log('Results body:', JSON.stringify(results, null, 2));
    console.log('Results count:', results.results?.length || 0);

    const query = await this.$searchDB.addResults(queryId, results.results);
    if (query) {
      console.log('=== UPDATING QUERY STATUS TO IDLE ===');
      await this.$searchDB.updateQueryStatus(
        query.queryId,
        SearchQueryStatus.IDLE,
      );

      const enrichedQuery = await this.enrichQueryWithVideos(query);
      console.log('=== EMITTING SOCKET UPDATE ===');
      console.log('Enriched query:', JSON.stringify(enrichedQuery, null, 2));
      Logger.log(
        `Emitting SEARCH_UPDATE socket for ${queryId} with ${results.results.length} results`,
      );
      this.$emitter.emit(SocketEvent.SEARCH_UPDATE, enrichedQuery);
      return enrichedQuery;
    }
    return query;
  }

  @OnEvent(SearchEvents.EMBEDDINGS_UPDATE)
  async syncSearches() {
    const queries = await this.$searchDB.readAll();

    const queriesOnWatch: SearchQuery[] = queries.filter(
      (query) => query.watch,
    );

    if (queriesOnWatch.length > 0) {
      const reRunPromises = queriesOnWatch.map((query) =>
        this.reRunQuery(query.queryId),
      );

      await Promise.all(reRunPromises);
      this.$emitter.emit(SocketEvent.SEARCH_NOTIFICATION);
    }
  }
}
