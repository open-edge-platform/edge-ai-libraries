// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';

export type ExampleStatus = 'idle' | 'running' | 'error';

export interface ExampleRecord {
  dbId?: number;
  exampleId: string;
  title: string;
  status: ExampleStatus;
  metadata?: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
}

export class ExampleDTO {
  @ApiProperty({ description: 'Human-readable title for the example item' })
  title: string;

  @ApiPropertyOptional({ description: 'Optional feature-specific metadata' })
  metadata?: Record<string, unknown>;
}

export interface ExampleRO {
  exampleId: string;
}

export class ExampleROSwagger implements ExampleRO {
  @ApiProperty({ description: 'ID of the created example item' })
  exampleId: string;
}
