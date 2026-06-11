// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Controller, Get } from '@nestjs/common';
import { AppService } from './app.service';
import { AppConfigService } from './video-upload/services/app-config.service';
import { FeaturesService } from './features/features.service';
import { Features, FeaturesRO } from './features/features.model';
import { SystemConfigWithMeta } from './video-upload/models/upload.model';
import { ApiOkResponse, ApiOperation, ApiTags } from '@nestjs/swagger';

@ApiTags('App')
@Controller('app')
export class AppController {
  constructor(
    private $appConfig: AppConfigService,
    private $feature: FeaturesService,
  ) {}

  @Get('config')
  @ApiOperation({ summary: 'Get default system configuration' })
  @ApiOkResponse({ description: 'System configuration' })
  async getSystemConfig(): Promise<SystemConfigWithMeta> {
    return await this.$appConfig.systemConfigWithMeta();
  }

  @Get('features')
  @ApiOperation({ summary: 'Get enabled features' })
  @ApiOkResponse({ description: 'Feature flags', type: FeaturesRO })
  getFeatures(): Features {
    return this.$feature.getFeatures();
  }
}
