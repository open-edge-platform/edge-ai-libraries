// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { Module } from '@nestjs/common';
import { VlmService } from './services/vlm.service';
import { LlmService } from './services/llm.service';
import { ConfigModule } from '@nestjs/config';
import { DatastoreModule } from 'src/datastore/datastore.module';
import { TemplateService } from './services/template.service';
import { VlmController } from './controllers/vlm.controller';
import { LlmController } from './controllers/llm.controller';
import { OpenaiHelperService } from './services/openai-helper.service';
import { FeaturesModule } from 'src/features/features.module';

@Module({
  imports: [ConfigModule, DatastoreModule, FeaturesModule],
  providers: [VlmService, LlmService, TemplateService, OpenaiHelperService],
  exports: [LlmService, VlmService, TemplateService],
  controllers: [VlmController, LlmController],
})
export class LanguageModelModule {}
