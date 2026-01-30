// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Module } from '@nestjs/common';
import { TelemetryService } from './telemetry.service';
import { TelemetryController } from './telemetry.controller';
import { DataprepTelemetryService } from './dataprep-telemetry.service';

@Module({
  controllers: [TelemetryController],
  providers: [TelemetryService, DataprepTelemetryService],
  exports: [TelemetryService],
})
export class TelemetryModule {}
