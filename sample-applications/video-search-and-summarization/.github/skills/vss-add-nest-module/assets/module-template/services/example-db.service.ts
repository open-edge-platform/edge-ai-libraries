// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { ExampleEntity } from '../models/example.entity';
import { ExampleRecord } from '../models/example.model';

@Injectable()
export class ExampleDbService {
  constructor(
    @InjectRepository(ExampleEntity)
    private exampleRepo: Repository<ExampleEntity>,
  ) {}

  async create(example: ExampleRecord): Promise<ExampleEntity> {
    const newExample = this.exampleRepo.create(example);
    return this.exampleRepo.save(newExample);
  }

  async readAll(): Promise<ExampleEntity[]> {
    return await this.exampleRepo.find();
  }

  async read(exampleId: string): Promise<ExampleEntity | null> {
    const example = await this.exampleRepo.findOne({ where: { exampleId } });
    return example ?? null;
  }

  async update(exampleId: string, example: Partial<ExampleRecord>): Promise<ExampleEntity | null> {
    let existingExample = await this.read(exampleId);
    if (!existingExample) {
      return null;
    }

    existingExample = {
      ...existingExample,
      ...example,
      updatedAt: new Date().toISOString(),
    };

    return this.exampleRepo.save(existingExample);
  }
}
