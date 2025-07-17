// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { HttpsProxyAgent } from 'https-proxy-agent';
import OpenAI, { ClientOptions } from 'openai';

export interface OpenAiInitRO {
  proxyAgent?: HttpsProxyAgent<string>;
  openAiConfig: Partial<ClientOptions>;
  client: OpenAI;
}
