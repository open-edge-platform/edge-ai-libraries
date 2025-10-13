// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Module } from '@nestjs/common';
import { AudioService } from './services/audio.service';
import { HttpModule } from '@nestjs/axios';
import { DatastoreModule } from 'src/datastore/datastore.module';
import { AudioController } from './controllers/audio.controller';

@Module({
  imports: [HttpModule, DatastoreModule],
  providers: [AudioService],
  exports: [AudioService],
  controllers: [AudioController],
})
export class AudioModule {}
