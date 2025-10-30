// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Injectable, Logger } from '@nestjs/common';
import {
  SearchQuery,
  SearchQueryStatus,
  SearchResultBody,
  SearchShimQuery,
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

  async getQueries() {
    const queries = await this.$searchDB.readAll();

    // Enrich each query with video information
    const enrichedQueries = await Promise.all(
      queries.map((query) => this.enrichQueryWithVideos(query)),
    );

    return enrichedQueries.filter((query) => query !== null);
  }

  async newQuery(query: string, tags: string[] = []) {
    const searchQuery: SearchQuery = {
      queryId: uuidV4(),
      query,
      watch: false,
      results: [],
      tags,
      queryStatus: SearchQueryStatus.RUNNING,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };

    Logger.log('Search Query', searchQuery);

    const res = await this.$searchDB.create(searchQuery);

    this.$emitter.emit(SearchEvents.RUN_QUERY, res.queryId);

    return res;
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

    return query as SearchQuery;
  }

  async addToWatch(queryId: string) {
    await this.$searchDB.updateWatch(queryId, true);
  }

  async removeFromWatch(queryId: string) {
    await this.$searchDB.updateWatch(queryId, false);
  }

  @OnEvent(SearchEvents.RUN_QUERY)
  async reRunQuery(queryId: string) {
    const query = await this.$searchDB.read(queryId);
    if (!query) {
      throw new Error(`Query with ID ${queryId} not found`);
    }

    const updatedQuery = await this.$searchDB.updateQueryStatus(
      queryId,
      SearchQueryStatus.RUNNING,
    );
    const enrichedQuery = await this.enrichQueryWithVideos(updatedQuery);
    this.$emitter.emit(SocketEvent.SEARCH_UPDATE, enrichedQuery);

    try {
      console.log('=== RUNNING SEARCH ===');
      console.log(`Query ID: ${queryId}, Query: ${query}, Tags: ${JSON.stringify(query.tags)}`);
      
      const results = await this.runSearch(queryId, query.query, query.tags);
      
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
          console.log('Relevant results count:', relevantResults.results?.length || 0);
        } else {
          console.log('Available query_ids in results:', results.results.map(r => r.query_id));
        }

        if (relevantResults) {
          console.log('=== UPDATING RESULTS ===');
          const freshEntity = await this.updateResults(
            queryId,
            relevantResults,
          );
          console.log('Fresh entity after update:', JSON.stringify(freshEntity, null, 2));
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
      console.log('Updated query with error:', JSON.stringify(updatedQuery, null, 2));
      const enrichedQuery = await this.enrichQueryWithVideos(updatedQuery);
      this.$emitter.emit(SocketEvent.SEARCH_UPDATE, enrichedQuery);
      return null;
    }
  }

  async runSearch(queryId: string, query: string, tags: string[]) {
    const queryShim: SearchShimQuery = {
      query,
      query_id: queryId,
      tags,
    };

    console.log('=== SEARCH STATE SERVICE ===');
    console.log('Running search with payload:', JSON.stringify([queryShim], null, 2));

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
      this.$emitter.emit(SocketEvent.SEARCH_UPDATE, enrichedQuery);
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
