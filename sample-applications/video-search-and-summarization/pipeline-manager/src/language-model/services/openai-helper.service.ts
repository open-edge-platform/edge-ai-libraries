// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Injectable, Logger } from '@nestjs/common';
import { OpenAiInitRO } from '../models/openai.model';
import { ConfigService } from '@nestjs/config';
import OpenAI, { ClientOptions } from 'openai';
import { HttpsProxyAgent } from 'https-proxy-agent';

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
}
