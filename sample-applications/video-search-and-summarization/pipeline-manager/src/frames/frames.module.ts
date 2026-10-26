// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { HttpModule } from '@nestjs/axios';
import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { FrameController } from './controllers/frame.controller';
import { FrameShimService } from './services/frame-shim.service';

/**
 * On-demand single-frame retrieval.
 *
 * Stateless validating proxy over multimodal-dataprep's `GET /media/frame`:
 * dataprep decodes a frame on demand and never persists it, so there is no
 * entity or cache to own here.
 */
@Module({
  imports: [ConfigModule, HttpModule],
  controllers: [FrameController],
  providers: [FrameShimService],
  exports: [FrameShimService],
})
export class FramesModule {}
