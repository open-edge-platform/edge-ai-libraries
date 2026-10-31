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
    imageSearchEnabled: false,
  };
  private static readonly IMAGE_SEARCH_INDEX = 'video_frame_embeddings';

  constructor(private $config: ConfigService) {
    this.features.summary =
      this.$config.get<FEATURE_STATE>('features.summary')!;
    this.features.search = this.$config.get<FEATURE_STATE>('features.search')!;
    const vsIndexName = this.$config.get<string>('search.vsIndexName');
    // Whether a frame-embedding index (rather than a caption-embedding-only
    // one, as used in unified mode) is deployed. This is the same signal
    // that gates image search, and is also what distinguishes dual mode
    // (fast, independent search indexing available) from unified mode
    // (search indexing must go through the summary/caption path).
    this.features.imageSearchEnabled =
      this.features.search === FEATURE_STATE.ON &&
      vsIndexName === FeaturesService.IMAGE_SEARCH_INDEX;
  }

  getFeatures(): Features {
    return this.features;
  }

  hasFeature(feature: 'summary' | 'search'): boolean {
    return this.features[feature] === FEATURE_STATE.ON;
  }

  isImageSearchEnabled(): boolean {
    return this.features.imageSearchEnabled;
  }
}
