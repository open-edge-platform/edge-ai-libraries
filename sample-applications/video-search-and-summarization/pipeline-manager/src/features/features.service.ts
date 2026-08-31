// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Injectable } from '@nestjs/common';
import { FEATURE_STATE, Features } from './features.model';
import { ConfigService } from '@nestjs/config';

export enum FeaturesEnum {
  SUMMARY = 'summary',
  SEARCH = 'search',
}

@Injectable()
export class FeaturesService {
  features: Features = {
    [FeaturesEnum.SUMMARY]: FEATURE_STATE.OFF,
    [FeaturesEnum.SEARCH]: FEATURE_STATE.OFF,
  };
  private imageSearchEnabled = false;
  private static readonly IMAGE_SEARCH_INDEX = 'video_frame_embeddings';

  constructor(private $config: ConfigService) {
    this.features.summary =
      this.$config.get<FEATURE_STATE>('features.summary')!;
    this.features.search = this.$config.get<FEATURE_STATE>('features.search')!;
    const vsIndexName = this.$config.get<string>('search.vsIndexName');
    this.imageSearchEnabled =
      this.features.search === FEATURE_STATE.ON &&
      vsIndexName === FeaturesService.IMAGE_SEARCH_INDEX;
  }

  getFeatures(): Features {
    return this.features;
  }

  hasFeature(feature: keyof Features): boolean {
    return this.features[feature] === FEATURE_STATE.ON;
  }

  isImageSearchEnabled(): boolean {
    return this.imageSearchEnabled;
  }
}
