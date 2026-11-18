// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Injectable, Logger } from '@nestjs/common';
import { OnEvent } from '@nestjs/event-emitter';
import { StreamEvents } from 'src/events/Pipeline.events';
import { TagsDbService } from './tags-db.service';

@Injectable()
export class TagsService {
  /** Live-stream tags already in the table; skips the write on every poll. */
  private registeredStreamTags = new Set<string>();
  private registeringStreamTags = false;

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

  /**
   * Live-stream tags are stored by dataprep, not here, so `GET /tags` would
   * miss them. The stream poller reports them on every tick; only unseen tags
   * hit the database, one write at a time (the table has no unique
   * constraint). A failed write is logged and retried on the next tick.
   */
  @OnEvent(StreamEvents.TAGS_SEEN)
  async onStreamTags(tags: string[]) {
    const unseen = tags
      .map((tag) => tag.trim())
      .filter((tag) => tag && !this.registeredStreamTags.has(tag));
    if (!unseen.length || this.registeringStreamTags) {
      return;
    }
    this.registeringStreamTags = true;
    try {
      await this.addTags(unseen);
      unseen.forEach((tag) => this.registeredStreamTags.add(tag));
    } catch (error) {
      Logger.warn(
        `Could not register live stream tags: ${
          error instanceof Error ? error.message : String(error)
        }`,
        TagsService.name,
      );
    } finally {
      this.registeringStreamTags = false;
    }
  }
}
