// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { ApiProperty } from '@nestjs/swagger';

export class TelemetryStatusRO {
  @ApiProperty({ description: 'Whether the telemetry collector is connected' })
  collectorConnected: boolean;

  @ApiProperty({ description: 'Status message' })
  message: string;
}
