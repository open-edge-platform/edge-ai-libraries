// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Module } from '@nestjs/common';
import { EvamService } from './services/evam.service';
import { RabbitmqService } from './services/rabbitmq.service';
import { HttpModule } from '@nestjs/axios';
import { DatastoreModule } from 'src/datastore/datastore.module';
import { FeaturesModule } from 'src/features/features.module';

@Module({
  imports: [HttpModule, DatastoreModule, FeaturesModule],
  providers: [EvamService, RabbitmqService],
  exports: [EvamService],
})
export class EvamModule {}
