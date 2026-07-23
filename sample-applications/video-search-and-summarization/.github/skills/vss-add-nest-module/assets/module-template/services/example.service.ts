// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Injectable, NotFoundException } from '@nestjs/common';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { v4 as uuidV4 } from 'uuid';
import { ExampleDTO, ExampleRO } from '../models/example.model';
import { ExampleDbService } from './example-db.service';

@Injectable()
export class ExampleService {
  constructor(
    private $exampleDb: ExampleDbService,
    private $emitter: EventEmitter2,
  ) {}

  async getExample(exampleId: string) {
    const example = await this.$exampleDb.read(exampleId);
    if (!example) {
      throw new NotFoundException('Example not found');
    }
    return example;
  }

  async createExample(reqBody: ExampleDTO): Promise<ExampleRO> {
    const exampleId = uuidV4();
    const example = await this.$exampleDb.create({
      exampleId,
      title: reqBody.title,
      status: 'idle',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    });

    // Prefer adding a real enum in src/events/Pipeline.events.ts instead of emitting string literals.
    // this.$emitter.emit(ExampleEvents.CREATED, { exampleId: example.exampleId });

    return { exampleId: example.exampleId };
  }
}
