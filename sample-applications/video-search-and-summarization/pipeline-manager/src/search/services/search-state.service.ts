// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Injectable, Logger } from '@nestjs/common';
import {
  SearchQuery,
  SearchQueryStatus,
  SearchResultBody,
  SearchShimQuery,
} from '../model/search.model';
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
    let queries = await this.$searchDB.readAll();

    const videos = await this.$video.getVideos();

    const videosKeyedById = videos.reduce(
      (acc, video) => {
        acc[video.videoId] = video;
        return acc;
      },
      {} as Record<string, VideoEntity>,
    );

    queries = queries.map((query) => {
      if (query.results && query.results.length > 0) {
        query.results = query.results.map((result) => {
          const video = videosKeyedById[result.metadata.video_id];
          if (video) {
            result.video = video;
          }
          return result;
        });
      }
      return query;
    });

    return queries;
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
    this.$emitter.emit(SocketEvent.SEARCH_UPDATE, updatedQuery);

    try {
      const results = await this.runSearch(queryId, query.query, query.tags);
      if (results.results.length > 0) {
        const relevantResults = results.results.find(
          (el) => el.query_id === queryId,
        );

        if (relevantResults) {
          const freshEntity = await this.updateResults(
            queryId,
            relevantResults,
          );
          return freshEntity;
        }
        return null;
      } else {
        Logger.warn(`No results found for query ID ${queryId}`);
        return null;
      }
    } catch (error) {
      Logger.error(`Error running search for query ID ${queryId}`, error);
      const updatedQuery = await this.$searchDB.updateQueryStatus(
        queryId,
        SearchQueryStatus.IDLE,
      );
      this.$emitter.emit(SocketEvent.SEARCH_UPDATE, updatedQuery);
    }
  }

  async runSearch(queryId: string, query: string, tags: string[]) {
    const queryShim: SearchShimQuery = {
      query,
      query_id: queryId,
      tags,
    };

    const results = await lastValueFrom(this.$searchShim.search([queryShim]));

    return results.data || { results: [] };
  }

  async updateResults(queryId: string, results: SearchResultBody) {
    const query = await this.$searchDB.addResults(queryId, results.results);
    if (query) {
      await this.$searchDB.updateQueryStatus(
        query.queryId,
        SearchQueryStatus.IDLE,
      );

      this.$emitter.emit(SocketEvent.SEARCH_UPDATE, query);
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
