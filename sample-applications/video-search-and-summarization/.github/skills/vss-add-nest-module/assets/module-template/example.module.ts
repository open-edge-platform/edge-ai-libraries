// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { ExampleController } from './controllers/example.controller';
import { ExampleEntity } from './models/example.entity';
import { ExampleDbService } from './services/example-db.service';
import { ExampleService } from './services/example.service';
import { ExampleQueueService } from './queues/example-queue.service';

@Module({
  imports: [TypeOrmModule.forFeature([ExampleEntity])],
  controllers: [ExampleController],
  providers: [ExampleService, ExampleDbService, ExampleQueueService],
  exports: [ExampleService],
})
export class ExampleModule {}
