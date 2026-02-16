// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { SearchEntity } from '../model/search.entity';
import { Repository } from 'typeorm';
import {
  SearchQuery,
  SearchQueryStatus,
  SearchResult,
  TimeFilterSelection,
} from '../model/search.model';

@Injectable()
export class SearchDbService {
  constructor(
    @InjectRepository(SearchEntity)
    private searchRepo: Repository<SearchEntity>,
  ) {}

  private applyTimeFilterFields(
    target: SearchEntity,
    timeFilter?: TimeFilterSelection | null,
  ): void {
    if (timeFilter === undefined) {
      return;
    }
    target.timeFilterValue = timeFilter?.value ?? null;
    target.timeFilterUnit = timeFilter?.unit ?? null;
    target.timeFilterStart = timeFilter?.start ?? null;
    target.timeFilterEnd = timeFilter?.end ?? null;
  }

  async create(search: SearchQuery): Promise<SearchEntity> {
    const newSearch = this.searchRepo.create({
      ...search,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    });
    this.applyTimeFilterFields(newSearch, search.timeFilter);
    return this.searchRepo.save(newSearch);
  }

  async updateQueryStatus(
    queryId: string,
    status: SearchQueryStatus,
  ): Promise<SearchEntity | null> {
    const search = await this.read(queryId);
    if (!search) {
      return null;
    }
    search.queryStatus = status;
    search.updatedAt = new Date().toISOString();
    // Clear error message if status is not ERROR
    if (status !== SearchQueryStatus.ERROR) {
      search.errorMessage = undefined;
    }
    return this.searchRepo.save(search);
  }

  async updateQueryStatusWithError(
    queryId: string,
    status: SearchQueryStatus,
    errorMessage?: string,
  ): Promise<SearchEntity | null> {
    const search = await this.read(queryId);
    if (!search) {
      return null;
    }
    search.queryStatus = status;
    search.errorMessage = errorMessage;
    search.updatedAt = new Date().toISOString();
    return this.searchRepo.save(search);
  }

  async readAll(): Promise<SearchEntity[]> {
    const searches = await this.searchRepo.find();
    return searches ?? [];
  }

  async readAllWatched(): Promise<SearchEntity[]> {
    const searches = await this.searchRepo.find({
      where: { watch: true },
    });
    return searches ?? [];
  }

  async read(queryId: string): Promise<SearchEntity | null> {
    const search = await this.searchRepo.findOne({
      where: { queryId },
    });
    return search ?? null;
  }

  async addResults(queryId: string, results: SearchResult[]) {
    const search = await this.read(queryId);
    if (!search) {
      return null;
    }
    search.results = [...results];
    search.updatedAt = new Date().toISOString();
    search.queryStatus = SearchQueryStatus.IDLE;
    return this.searchRepo.save(search);
  }

  async updateWatch(queryId: string, watch: boolean) {
    const search = await this.read(queryId);
    if (!search) {
      return null;
    }
    search.watch = watch;
    search.updatedAt = new Date().toISOString();
    return this.searchRepo.save(search);
  }

  async update(
    queryId: string,
    search: Partial<SearchQuery>,
  ): Promise<SearchEntity | null> {
    let existingSearch = await this.read(queryId);
    if (!existingSearch) {
      return null;
    }
    existingSearch = {
      ...existingSearch,
      ...search,
      updatedAt: new Date().toISOString(),
    };
    this.applyTimeFilterFields(existingSearch, search.timeFilter);
    return this.searchRepo.save(existingSearch);
  }

  async remove(queryId: string): Promise<void> {
    const search = await this.read(queryId);
    if (!search) {
      return;
    }
    await this.searchRepo.remove(search);
  }
}
