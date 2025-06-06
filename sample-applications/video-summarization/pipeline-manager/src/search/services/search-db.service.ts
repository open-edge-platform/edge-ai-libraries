import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { SearchEntity } from '../model/search.entity';
import { Repository } from 'typeorm';
import { SearchQuery, SearchResult } from '../model/search.model';

@Injectable()
export class SearchDbService {
  constructor(
    @InjectRepository(SearchEntity)
    private searchRepo: Repository<SearchEntity>,
  ) {}

  async create(search: SearchQuery): Promise<SearchEntity> {
    const newSearch = this.searchRepo.create({
      ...search,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    });
    return this.searchRepo.save(newSearch);
  }

  async readAll(): Promise<SearchEntity[]> {
    const searches = await this.searchRepo.find();
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
