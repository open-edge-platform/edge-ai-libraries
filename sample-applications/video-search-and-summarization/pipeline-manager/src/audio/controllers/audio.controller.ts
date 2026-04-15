// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Controller, Get } from '@nestjs/common';
import { AudioService } from '../services/audio.service';
import { lastValueFrom } from 'rxjs';
import { ApiOkResponse, ApiOperation, ApiTags } from '@nestjs/swagger';
import { AudioModelROSwagger } from '../models/audio.model';

@ApiTags('Audio')
@Controller('audio')
export class AudioController {
  constructor(private $audio: AudioService) {}

  @Get('models')
  @ApiOperation({ summary: 'Get available audio models' })
  @ApiOkResponse({
    description: 'Fetch available audio models',
    type: AudioModelROSwagger,
  })
  async getAudioModels() {
    const audioModels = await lastValueFrom(this.$audio.fetchModels());
    return audioModels.data;
  }
}
