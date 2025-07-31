// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Controller, Get } from '@nestjs/common';
import { AudioService } from '../services/audio.service';
import { lastValueFrom } from 'rxjs';
import { ApiOkResponse } from '@nestjs/swagger';
import { AudioModelROSwagger } from '../models/audio.model';

@Controller('audio')
export class AudioController {
  constructor(private $audio: AudioService) {}

  @Get('models')
  @ApiOkResponse({
    description: 'Fetch available audio models',
    type: AudioModelROSwagger,
  })
  async getAudioModels() {
    const audioModels = await lastValueFrom(this.$audio.fetchModels());
    return audioModels.data;
  }
}
