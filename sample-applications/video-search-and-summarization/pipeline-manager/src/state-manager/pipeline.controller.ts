// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Controller, Get, Req } from '@nestjs/common';
import { ChunkingService } from './queues/chunking.service';
import { EvamService } from 'src/evam/services/evam.service';
import { ApiOkResponse } from '@nestjs/swagger';

@Controller('pipeline')
export class PipelineController {
  constructor(
    private $chunking: ChunkingService,
    private $evam: EvamService,
  ) {}

  @Get('frames')
  @ApiOkResponse({
    description: 'Get the current status of the frame processing pipeline',
  })
  getFramesPipeline(@Req() req: Request) {
    return {
      waiting: this.$chunking.waiting,
      processing: this.$chunking.processing,
    };
  }

  @Get('evam')
  @ApiOkResponse({ description: 'Get the current status of the EVAM pipeline' })
  getEvamPipeline() {
    return { chunkingInProgress: this.$evam.inProgress };
  }
}
