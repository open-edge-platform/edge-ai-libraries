// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Injectable, Logger } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { TagEntity } from '../models/tags.entity';
import { Repository } from 'typeorm';

@Injectable()
export class TagsDbService {
  constructor(
    @InjectRepository(TagEntity) private tagRepo: Repository<TagEntity>,
  ) {}

  async create(tags: string): Promise<TagEntity> {
    Logger.log('Adding tag to database', tags);
    const newTag = this.tagRepo.create({ tag: tags });
    return this.tagRepo.save(newTag);
  }

  async createMany(tags: string[]) {
    Logger.log('Adding multiple tags to database', tags);
    const newTags = tags.map((tag) => this.tagRepo.create({ tag }));
    return this.tagRepo.save(newTags);
  }

  async readAll(): Promise<TagEntity[]> {
    const tags = await this.tagRepo.find();
    return tags;
  }

  async read(tagId: number): Promise<TagEntity | null> {
    const tag = await this.tagRepo.findOne({
      where: { dbId: tagId },
    });
    return tag ?? null;
  }

  async remove(tagId: number) {
    Logger.log('Removing tag from database', tagId);
    const tag = await this.tagRepo.findOne({
      where: { dbId: tagId },
    });
    if (!tag) {
      return null;
    }
    return this.tagRepo.remove(tag);
  }
}
