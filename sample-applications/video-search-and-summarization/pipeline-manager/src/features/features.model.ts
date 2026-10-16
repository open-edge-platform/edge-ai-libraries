// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { ApiProperty, ApiResponseProperty } from '@nestjs/swagger';

export interface Features {
  summary: FEATURE_STATE;
  search: FEATURE_STATE;
  imageSearchEnabled: boolean;
}

export class FeaturesRO implements Features {
  @ApiProperty({
    type: String,
  })
  summary: FEATURE_STATE;
  @ApiResponseProperty({ type: String })
  search: FEATURE_STATE;
  @ApiResponseProperty({ type: Boolean })
  imageSearchEnabled: boolean;
}

export enum CONFIG_STATE {
  ON = 'CONFIG_ON',
  OFF = 'CONFIG_OFF',
}

export enum FEATURE_STATE {
  ON = 'FEATURE_ON',
  OFF = 'FEATURE_OFF',
}
