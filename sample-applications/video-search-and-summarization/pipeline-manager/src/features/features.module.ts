// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Module } from '@nestjs/common';
import { FeaturesService } from './features.service';

@Module({
  providers: [FeaturesService],
  exports: [FeaturesService],
})
export class FeaturesModule {}
