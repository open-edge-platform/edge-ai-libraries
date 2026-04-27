// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Controller, Get } from '@nestjs/common';
import { TelemetryService } from './telemetry.service';
import { ApiOkResponse, ApiOperation, ApiTags } from '@nestjs/swagger';
import { TelemetryStatusRO } from './telemetry.model';

@ApiTags('Metrics')
@Controller('metrics')
export class TelemetryController {
  constructor(private readonly telemetry: TelemetryService) {}

  @Get('status')
  @ApiOperation({ summary: 'Get telemetry collector connection status' })
  @ApiOkResponse({ description: 'Telemetry collector status', type: TelemetryStatusRO })
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
