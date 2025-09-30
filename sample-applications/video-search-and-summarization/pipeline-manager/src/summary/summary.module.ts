// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Module } from '@nestjs/common';
import { SummaryService } from './services/summary.service';
import { VideoUploadModule } from 'src/video-upload/video-upload.module';
import { StateManagerModule } from 'src/state-manager/state-manager.module';
import { SummaryController } from './controllers/summary.controller';

@Module({
  imports: [VideoUploadModule, StateManagerModule],
  controllers: [SummaryController],
  providers: [SummaryService],
})
export class SummaryModule {}
