// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Injectable } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { TemplateService } from 'src/language-model/services/template.service';
import { SystemConfig, SystemConfigWithMeta } from '../models/upload.model';
import { EVAMPipelines } from 'src/evam/models/evam.model';
import { EvamService } from 'src/evam/services/evam.service';
import { AudioService } from 'src/audio/services/audio.service';
import { lastValueFrom } from 'rxjs';
import { AudioModelRO } from 'src/audio/models/audio.model';

@Injectable()
export class AppConfigService {
  constructor(
    private $config: ConfigService,
    private $template: TemplateService,
    private $evam: EvamService,
    private $audio: AudioService,
  ) {}

  systemConfig(): SystemConfig {
    const useCase = this.$config.get<string>('openai.usecase')!;

    const systemConfig: SystemConfig = {
      frameOverlap: this.$config.get<number>(
        'openai.vlmCaptioning.frameOverlap',
      )!,
      evamPipeline: EVAMPipelines.OBJECT_DETECTION,
      multiFrame: this.$config.get<number>('openai.vlmCaptioning.multiFrame')!,
      framePrompt: this.$template.getTemplate(`${useCase}Frames`),
      summaryMapPrompt: this.$template.getTemplate(`${useCase}Summary`),
      summaryReducePrompt: this.$template.getTemplate(`${useCase}Reduce`),
      summarySinglePrompt: this.$template.getTemplate(`${useCase}Single`),
    };

    return systemConfig;
  }

  async systemConfigWithMeta(): Promise<SystemConfigWithMeta> {
    const systemConfig = this.systemConfig();
    const evamPipelines = this.$evam.availablePipelines();

    let audioModels: AudioModelRO | null = null;

    try {
      const audioHost = this.$config.get<string>('audio.host');
      if (audioHost) {
        const res = await lastValueFrom(this.$audio.fetchModels());
        audioModels = res.data;
      }
    } catch (error) {
      console.log('Audio not available');
      console.log('Audio Error', error);
    }

    const config: SystemConfigWithMeta = {
      ...systemConfig,
      meta: { evamPipelines, audioModels: [] },
    };

    if (audioModels) {
      config.meta = {
        ...config.meta,
        defaultAudioModel: audioModels.default_model,
        audioModels: audioModels.models,
      };
    }

    return config;
  }
}
