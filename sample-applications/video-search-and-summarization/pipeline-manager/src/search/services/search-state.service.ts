import { Injectable, Logger } from '@nestjs/common';
import {
  SearchQuery,
  SearchResult,
  SearchResultBody,
  SearchResultRO,
  SearchShimQuery,
} from '../model/search.model';
import { SearchDbService } from './search-db.service';
import { EventEmitter2, OnEvent } from '@nestjs/event-emitter';
import { SocketEvent } from 'src/events/socket.events';
import { SearchEvents } from 'src/events/Pipeline.events';
import { SearchShimService } from './search-shim.service';
import { lastValueFrom } from 'rxjs';
import { v4 as uuidV4 } from 'uuid';

@Injectable()
export class SearchStateService {
  constructor(
    private $searchDB: SearchDbService,
    private $emitter: EventEmitter2,
    private $searchShim: SearchShimService,
  ) {}

  async newQuery(query: string, tags: string[] = []) {
    const searchQuery: SearchQuery = {
      queryId: uuidV4(),
      query,
      watch: false,
      results: [],
      tags,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };

    Logger.log('Search', searchQuery);

    console.log(searchQuery);

    const res = await this.$searchDB.create(searchQuery);
    return res;
  }

  async addToWatch(queryId: string) {
    await this.$searchDB.updateWatch(queryId, true);
  }

  async removeFromWatch(queryId: string) {
    await this.$searchDB.updateWatch(queryId, false);
  }

  async updateResults(queryId: string, results: SearchResultBody) {
    const query = await this.$searchDB.addResults(queryId, results.results);
    if (query) {
      if (query.watch) {
        this.$emitter.emit(SocketEvent.SEARCH_NOTIFICATION, { queryId });
      }
    }
    return query;
  }

  @OnEvent(SearchEvents.EMBEDDINGS_UPDATE)
  async syncSearches() {
    const queries = await this.$searchDB.readAll();

    const queriesOnWatch: SearchShimQuery[] = queries
      .filter((query) => query.watch)
      .map((curr) => ({ query_id: curr.queryId, query: curr.query }));

    const results = await lastValueFrom(
      this.$searchShim.search(queriesOnWatch),
    );

    if (results.data) {
    }
  }
}
