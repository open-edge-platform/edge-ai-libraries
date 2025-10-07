// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Controller, Delete, Get } from '@nestjs/common';
import { TagsService } from '../services/tags.service';
import { TagsDbService } from '../services/tags-db.service';
import { ApiOkResponse, ApiOperation, ApiParam } from '@nestjs/swagger';

@Controller('tags')
export class TagsController {
  constructor(
    private $tags: TagsService,
    private $tagsDB: TagsDbService,
  ) {}

  @Get('')
  @ApiOperation({ summary: 'Get all tags' })
  @ApiOkResponse({ description: 'Returns a list of all tags' })
  async getTags(): Promise<string[]> {
    return this.$tagsDB.readAll().then((tags) => tags.map((tag) => tag.tag));
  }

  @Delete(':tagId')
  @ApiOperation({ summary: 'Remove a tag by ID' })
  @ApiParam({
    name: 'tagId',
    type: 'number',
    description: 'ID of the tag to remove',
  })
  async removeTag(tagId: number) {
    if (!tagId) {
      throw new Error('Tag ID is required');
    }
    return this.$tagsDB.remove(tagId);
  }
}
