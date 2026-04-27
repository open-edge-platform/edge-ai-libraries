// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Injectable, Logger } from '@nestjs/common';
import { OpenAiInitRO } from '../models/openai.model';
import { ConfigService } from '@nestjs/config';
import OpenAI, { ClientOptions } from 'openai';
import { HttpsProxyAgent } from 'https-proxy-agent';

interface SelectModelOptions {
  availableModels: string[];
  configuredModelName?: string;
  configuredModelEnv: string;
  serviceLabel: string;
  disallowedSingleModelName?: string;
  disallowedSingleModelReason?: string;
  // Fallback model name when multiple models exist and configuredModelName is not set.
  // Used for shared-model deployments where LLM falls back to VLM model.
  fallbackModelName?: string;
}

@Injectable()
export class OpenaiHelperService {
  constructor(private $config: ConfigService) {}

  initializeClient(apiKey: string, baseURL: string): OpenAiInitRO {
    const proxyUrl: string | undefined = this.$config.get<string>('proxy.url');
    const noProxy: string = this.$config.get<string>('proxy.noProxy') || '';

    const openAiConfig: Partial<ClientOptions> = { apiKey, baseURL };
    const baseUrlHost = new URL(baseURL).hostname;

    let proxyAgent: HttpsProxyAgent<string> | null = null;

    if (
      proxyUrl &&
      typeof proxyUrl === 'string' &&
      (!noProxy || !noProxy.split(',').includes(baseUrlHost))
    ) {
      Logger.log('Adding proxy to openai client');
      proxyAgent = new HttpsProxyAgent(proxyUrl);
      openAiConfig.httpAgent = proxyAgent;
    }

    const client = new OpenAI(openAiConfig);

    let res: OpenAiInitRO = { openAiConfig, client };

    if (proxyAgent) {
      res = { ...res, proxyAgent };
    }

    return res;
  }

  getConfigUrl(
    openAIConfig: Partial<ClientOptions>,
    modelsApi: string,
  ): string | null {
    const { baseURL } = openAIConfig;

    if (baseURL) {
      const openAiBase = new URL(baseURL);

      const baseUrlHost = openAiBase.hostname;
      const baseUrlPort = openAiBase.port;
      const baseUrlProtocol = openAiBase.protocol;

      const configUrl = `${baseUrlProtocol}//${baseUrlHost}:${baseUrlPort}/${modelsApi}`;

      return configUrl;
    } else {
      return null;
    }
  }

  selectModel({
    availableModels,
    configuredModelName,
    configuredModelEnv,
    serviceLabel,
    disallowedSingleModelName,
    disallowedSingleModelReason,
    fallbackModelName,
  }: SelectModelOptions): string {
    if (availableModels.length === 0) {
      throw new Error('No models available');
    }

    // 1. If model is explicitly configured, use it (must exist in available models)
    const normalizedConfiguredModel = configuredModelName?.trim();
    if (normalizedConfiguredModel) {
      if (!availableModels.includes(normalizedConfiguredModel)) {
        throw new Error(
          `Configured ${serviceLabel} model '${normalizedConfiguredModel}' was not found. Available models: ${availableModels.join(', ')}`,
        );
      }
      return normalizedConfiguredModel;
    }

    // 2. If only one model available, use it (with optional disallow check)
    if (availableModels.length === 1) {
      const [singleModel] = availableModels;

      // This guard prevents auto-selecting an LLM-only model for VLM captioning
      // in OVMS split-model deployments where VLM_MODEL_NAME is required.
      if (
        disallowedSingleModelName?.trim() &&
        singleModel === disallowedSingleModelName.trim()
      ) {
        throw new Error(
          disallowedSingleModelReason ??
            `The only available model '${singleModel}' cannot be used for ${serviceLabel}.`,
        );
      }

      return singleModel;
    }

    // 3. Multiple models available: try fallback model if provided
    // This enables shared-model mode where LLM uses the VLM model when LLM_MODEL_NAME is not set.
    const normalizedFallback = fallbackModelName?.trim();
    if (normalizedFallback && availableModels.includes(normalizedFallback)) {
      Logger.log(
        `${serviceLabel}: Using fallback model '${normalizedFallback}' (shared-model mode)`,
      );
      return normalizedFallback;
    }

    // 4. No fallback available - require explicit configuration
    throw new Error(
      `Multiple models are available for ${serviceLabel}. Configure ${configuredModelEnv}.`,
    );
  }
}
