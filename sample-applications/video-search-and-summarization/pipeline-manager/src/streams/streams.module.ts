// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { HttpModule } from '@nestjs/axios';
import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { StreamsController } from './controllers/streams.controller';
import { StreamPollerService } from './services/stream-poller.service';
import { StreamShimService } from './services/stream-shim.service';

/**
 * Live (RTSP) stream ingestion.
 *
 * Deliberately stateless: multimodal-dataprep already persists stream
 * registrations and restores them across restarts, so this module is a
 * validating proxy plus an event pump. No TypeORM entity is registered.
 */
@Module({
  imports: [ConfigModule, HttpModule],
  controllers: [StreamsController],
  providers: [StreamShimService, StreamPollerService],
  exports: [StreamShimService, StreamPollerService],
})
export class StreamsModule {}
