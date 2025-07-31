// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Injectable } from '@nestjs/common';
import { TagsDbService } from './tags-db.service';

@Injectable()
export class TagsService {
  constructor(private $tagDB: TagsDbService) {}

  async addTags(tags: string[]) {
    const uniqueTags = Array.from(new Set(tags));
    if (uniqueTags.length === 0) {
      return;
    }

    const existingTags = await this.$tagDB.readAll();
    const existingTagNames = new Set(existingTags.map((tag) => tag.tag));

    const newTags = uniqueTags.filter((tag) => !existingTagNames.has(tag));
    if (newTags.length === 0) {
      return;
    }

    return await this.$tagDB.createMany(newTags);
  }
}
