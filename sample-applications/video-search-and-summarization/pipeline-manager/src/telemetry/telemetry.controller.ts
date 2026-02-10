// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Controller, Get } from '@nestjs/common';
import { TelemetryService } from './telemetry.service';

@Controller('metrics')
export class TelemetryController {
  constructor(private readonly telemetry: TelemetryService) {}

  @Get('status')
  status() {
    const status = this.telemetry.getStatus();
    return {
      ...status,
      message: status.collectorConnected
        ? 'Collector connected'
        : 'Collector unavailable; telemetry disabled',
    };
  }
}
