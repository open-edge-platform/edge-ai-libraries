// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Injectable } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';

export interface InferenceConfig {
  model: string;
  ip: string;
}

@Injectable()
export class InferenceCountService {
  private vlmProcessCount: number = 0;
  private llmProcessCount: number = 0;

  maxVlmConcurrent: number = this.$config.get<number>(
    'openai.vlmCaptioning.concurrent',
  )!; // Default max concurrent VLM processes
  maxLlmConcurrent: number = this.$config.get<number>(
    'openai.llmSummarization.concurrent',
  )!; // Default max concurrent LLM processes

  private useVlmForInference: boolean = false;

  private vlmConfig: InferenceConfig | null = null;
  private llmConfig: InferenceConfig | null = null;

  constructor(private $config: ConfigService) {}

  setVlmConfig(config: InferenceConfig) {
    this.vlmConfig = config;
    this.configEqualityCheck();
  }

  setLlmConfig(config: InferenceConfig) {
    this.llmConfig = config;
    this.configEqualityCheck();
  }

  getVlmCount() {
    return this.vlmProcessCount;
  }

  getLlmCount() {
    return this.llmProcessCount;
  }

  hasVlmSlots() {
    return this.vlmProcessCount < this.maxVlmConcurrent;
  }

  hasLlmSlots() {
    return this.useVlmForInference
      ? this.hasVlmSlots()
      : this.llmProcessCount < this.maxLlmConcurrent;
  }

  private configEqualityCheck() {
    if (!this.vlmConfig || !this.llmConfig) {
      this.useVlmForInference = false;
    } else if (
      this.vlmConfig.model === this.llmConfig.model &&
      this.vlmConfig.ip === this.llmConfig.ip
    ) {
      this.useVlmForInference = true;
    } else {
      this.useVlmForInference = false;
    }

    console.log('EQUALITY', this.useVlmForInference);
  }

  incrementVlmProcessCount() {
    this.vlmProcessCount++;
  }

  incrementLlmProcessCount() {
    this.llmProcessCount++;
    if (this.useVlmForInference) {
      this.incrementVlmProcessCount();
    }
  }

  decrementVlmProcessCount() {
    if (this.vlmProcessCount > 0) {
      this.vlmProcessCount--;
    }
  }

  decrementLlmProcessCount() {
    if (this.llmProcessCount > 0) {
      this.llmProcessCount--;
      if (this.useVlmForInference) {
        this.decrementVlmProcessCount();
      }
    }
  }
}
