// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import {
  Injectable,
  Logger,
  ServiceUnavailableException,
} from '@nestjs/common';
import { readFile } from 'node:fs/promises';
import { OpenAI } from 'openai';
import { ConfigService } from '@nestjs/config';
import { HttpsProxyAgent } from 'https-proxy-agent';
import {
  ChatCompletionContentPartImage,
  ChatCompletionMessageParam,
} from 'openai/resources';
import { DatastoreService } from 'src/datastore/services/datastore.service';
import { CompletionQueryParams } from '../models/completion.model';
import { TemplateService } from './template.service';
import { ModelInfo } from 'src/state-manager/models/state.model';
import { OpenaiHelperService } from './openai-helper.service';
import { FeaturesService } from 'src/features/features.service';
import { CONFIG_STATE } from 'src/features/features.model';
import { InferenceCountService } from './inference-count.service';

interface ImageCompletionParams extends CompletionQueryParams {
  user_query?: string;
  fileNameOrUrl: string;
}

interface MultiImageCompletionParams extends CompletionQueryParams {
  user_query?: string;
  fileNameOrUrl: string[];
}

interface ModelConfigResponse {
  [key: string]: {
    model_version_status: {
      version: string;
      state: string;
      status: {
        error_code: string;
        error_message: string;
      };
    }[];
  };
}

@Injectable()
export class VlmService {
  public client: OpenAI;
  public models: OpenAI.Models.Model[];
  public model: string;

  public serviceReady: boolean = false;

  constructor(
    private $openAiHelper: OpenaiHelperService,
    private $config: ConfigService,
    private $dataStore: DatastoreService,
    private $feature: FeaturesService,
    private $template: TemplateService,
    private $inferenceCount: InferenceCountService,
  ) {
    if ($feature.hasFeature('summary')) {
      this.initialize().catch((error) => {
        console.error('VlmService initialization failed:');
        throw error;
      });
      Logger.log('VLM service initialized successfully');
    }
  }

  private defaultParams(): CompletionQueryParams {
    const accessKey = ['openai', 'vlmCaptioning', 'defaults'].join('.');
    const params: CompletionQueryParams = {};
    // VLM captioning reads its own backend flag, which falls back to USE_VLLM.
    // Compose uses USE_VLLM for exclusive backend selection (OVMS-only or vLLM-only).
    const isVllm =
      this.$config.get('openai.vlmCaptioning.useVLLM') === CONFIG_STATE.ON;

    // For do_sample and seed parameters:
    // These are not supported by vLLM - skip them. Apply for OVMS-backed inference.
    if (!isVllm) {
      if (this.$config.get(`${accessKey}.doSample`) !== null) {
        params.do_sample = this.$config.get(`${accessKey}.doSample`)!;
      }
      if (this.$config.get(`${accessKey}.seed`) !== null) {
        params.seed = +this.$config.get(`${accessKey}.seed`)!;
      }
    }

    if (this.$config.get(`${accessKey}.temperature`)) {
      const configuredTemp = +this.$config.get(`${accessKey}.temperature`)!;
      params.temperature = isVllm && configuredTemp < 0.01 ? 0.01 : configuredTemp;
    } else if (isVllm) {
      params.temperature = 0.01;
    }
    if (this.$config.get(`${accessKey}.topP`)) {
      params.top_p = +this.$config.get(`${accessKey}.topP`)!;
    }
    if (this.$config.get(`${accessKey}.presencePenalty`)) {
      params.presence_penalty = +this.$config.get(
        `${accessKey}.presencePenalty`,
      )!;
    }
    if (this.$config.get(`${accessKey}.frequencyPenalty`)) {
      params.frequency_penalty = +this.$config.get(
        `${accessKey}.frequencyPenalty`,
      )!;
    }
    if (this.$config.get(`${accessKey}.maxCompletionTokens`)) {
      const maxTokens = +this.$config.get(
        `${accessKey}.maxCompletionTokens`,
      )!;
      params.max_completion_tokens = maxTokens;
      params.max_tokens = maxTokens;
    }

    return params;
  }

  private async initialize() {
    let configUrl: string | null = null;
    const fetchOptions: { agent?: HttpsProxyAgent<string> } = {};
    const apiKey: string = this.$config.get<string>(
      'openai.vlmCaptioning.apiKey',
    )!;
    const baseURL: string = this.$config.get<string>(
      'openai.vlmCaptioning.apiBase',
    )!;

    try {
      const { client, openAiConfig, proxyAgent } =
        this.$openAiHelper.initializeClient(apiKey, baseURL);
      this.client = client;

      if (proxyAgent) {
        fetchOptions.agent = proxyAgent;
      }

      const modelsApi = this.$config.get<string>(
        'openai.vlmCaptioning.modelsAPI',
      )!;
      configUrl = this.$openAiHelper.getConfigUrl(openAiConfig, modelsApi);
    } catch (error) {
      console.error('Failed to initialize OpenAI client:', error);
      throw error;
    }

    try {
      if (!configUrl) {
        throw new Error('Config URL is not available');
      }

      // OVMS serves model metadata from config; use it first when the backend supports it.
      await this.fetchModelsFromConfig(configUrl, fetchOptions);
      this.serviceReady = true;
      this.$inferenceCount.setVlmConfig({
        model: this.model,
        ip: baseURL,
      });
    } catch (error) {
      Logger.error(error);

      try {
        // vLLM is OpenAI-compatible but not OVMS-config-compatible, so use the
        // standard models API when config discovery is unavailable.
        await this.getModelsFromOpenai();
        this.serviceReady = true;
        this.$inferenceCount.setVlmConfig({
          model: this.model,
          ip: baseURL,
        });
      } catch (fallbackError) {
        Logger.error(fallbackError);
        throw new ServiceUnavailableException('Open AI fetch models failed');
      }
    }
  }

  private async fetchModelsFromConfig(
    url: string,
    fetchOptions: { agent?: HttpsProxyAgent<string> },
  ) {
    const response = await fetch(url, fetchOptions as RequestInit);
    if (!response.ok) {
      throw new Error(`Failed to retrieve model from endpoint: ${url}`);
    }

    const data: ModelConfigResponse =
      (await response.json()) as ModelConfigResponse;
    const modelKey = this.$openAiHelper.selectModel({
      availableModels: Object.keys(data),
      configuredModelName: this.$config.get<string>(
        'openai.vlmCaptioning.modelName',
      ),
      configuredModelEnv: 'VLM_MODEL_NAME',
      serviceLabel: 'VLM captioning',
      disallowedSingleModelName: this.$config.get<string>(
        'openai.llmSummarization.modelName',
      ),
      disallowedSingleModelReason:
        'VLM captioning requires VLM_MODEL_NAME when OVMS is configured with only the LLM model.',
    });

    if (data[modelKey].model_version_status[0].state === 'AVAILABLE') {
      this.model = modelKey;
      console.log(`Using VLM model: ${this.model}`);
    } else {
      console.warn(
        `model: ${modelKey} is in ${data[modelKey].model_version_status[0].state} state`,
      );
      this.model = modelKey;
    }
  }

  private async getModelsFromOpenai() {
    if (!this.client) {
      throw new Error('Client is not initialized');
    }

    const models = await this.client.models.list();
    console.log('Models', models);
    this.models = models.data;
    this.model = this.$openAiHelper.selectModel({
      availableModels: models.data.map((model) => model.id),
      configuredModelName: this.$config.get<string>(
        'openai.vlmCaptioning.modelName',
      ),
      configuredModelEnv: 'VLM_MODEL_NAME',
      serviceLabel: 'VLM captioning',
      disallowedSingleModelName: this.$config.get<string>(
        'openai.llmSummarization.modelName',
      ),
      disallowedSingleModelReason:
        'VLM captioning requires VLM_MODEL_NAME when OVMS is configured with only the LLM model.',
    });
    console.log(`Using model: ${this.model}`);
  }

  private async encodeBase64ContentFromUrl(fileNameOrUrl: string): Promise<string> {
    try {
      const objectName = this.getObjectNameFromUrl(fileNameOrUrl);
      const localPath = await this.$dataStore.getFile(objectName);
      const fileBuffer = await readFile(localPath);
      return fileBuffer.toString('base64');
    } catch (error) {
      throw new Error('Failed to fetch content');
    }
  }

  private getObjectNameFromUrl(fileNameOrUrl: string): string {
    try {
      const url = new URL(fileNameOrUrl);
      const objectPrefix = this.$dataStore.getObjectRelativePath('');
      if (!url.pathname.startsWith(objectPrefix)) {
        throw new Error('URL does not point to datastore object');
      }
      return decodeURIComponent(url.pathname.slice(objectPrefix.length));
    } catch {
      return fileNameOrUrl;
    }
  }

  public async runTextOnlyInference(
    user_query: string,
  ): Promise<string | null> {
    const startTime = Date.now();
    const chatCompletion = await this.client.chat.completions.create({
      messages: [
        {
          role: 'user',
          content: user_query,
        },
      ],
      model: this.model,
      ...this.defaultParams(),
    });

    const result = chatCompletion.choices[0].message.content;
    const endTime = Date.now();
    const timeTaken = (endTime - startTime) / 1000;
    console.log(`Time taken to run the code: ${timeTaken.toFixed(2)} seconds`);
    console.log('Chat completion output:', result);
    return result;
  }

  public getInferenceConfig(): ModelInfo {
    const device: string = this.$config.get<string>(
      'openai.vlmCaptioning.device',
    )!;
    return { device, model: this.model };
  }

  public async imageInference(
    userQuery: string,
    imageUri: string[],
  ): Promise<string | null> {
    try {
      this.$inferenceCount.incrementVlmProcessCount();
      console.log('Running VLM image inference', {
        queryLength: userQuery.length,
        imageCount: imageUri.length,
      });

      // Both vLLM and OVMS use image_url with direct URLs.
      // OVMS requires --allowed_media_domains to be configured with the MinIO host
      // (already set via OVMS_ALLOWED_MEDIA_DOMAINS in compose).
      const content: any[] = imageUri.map((url) => ({
        type: 'image_url',
        image_url: { url },
      }));

      const messages: any[] = [
        {
          role: 'user',
          // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
          content: [{ type: 'text', text: userQuery }, ...content],
        },
      ];

      const requestPayload = {
        messages,
        model: this.model,
        ...this.defaultParams(),
      };

      const completions = await this.client.chat.completions.create(requestPayload);

      let result: string | null = null;

      if (completions.choices.length > 0) {
        result = completions.choices[0].message.content;
      }

      this.$inferenceCount.decrementVlmProcessCount();
      return result;
    } catch (error) {
      this.$inferenceCount.decrementVlmProcessCount();
      console.log('ERROR Image Inference', error);
      throw error;
    }
  }

  private async runSingleImageInference(
    userQuery: string,
    fileNameOrUrl: string,
  ): Promise<string | null> {
    const imageBase64 = await this.encodeBase64ContentFromUrl(fileNameOrUrl);
    const chatCompletion = await this.client.chat.completions.create({
      messages: [
        {
          role: 'user',
          content: [
            {
              type: 'text',
              text: userQuery,
            },
            {
              type: 'image_url',
              image_url: {
                url: `data:image/jpeg;base64,${imageBase64}`,
              },
            },
          ],
        },
      ],
      model: this.model,
      ...this.defaultParams(),
    });

    return chatCompletion.choices[0].message.content;
  }

  public async runSingleImage(
    params: ImageCompletionParams,
  ): Promise<string | null> {
    const {
      user_query = this.$template.getFrameCaptionTemplateWithoutObjects(),
      fileNameOrUrl,
    } = params;

    const startTime = Date.now();
    const result = await this.runSingleImageInference(user_query, fileNameOrUrl);
    const endTime = Date.now();
    const timeTaken = (endTime - startTime) / 1000;
    console.log(`Time taken to run the code: ${timeTaken.toFixed(2)} seconds`);
    console.log('Chat completion output from base64 encoded image:', result);
    return result;
  }

  public async runMultiImage(
    params: MultiImageCompletionParams,
  ): Promise<void> {
    const {
      user_query = this.$template.getMultipleFrameCaptionTemplateWithoutObjects(),
      fileNameOrUrl,
    } = params;

    const imageBase64Promises = fileNameOrUrl.map((url) =>
      this.encodeBase64ContentFromUrl(url),
    );
    const imageBase64Array: string[] = await Promise.all(imageBase64Promises);

    const completions: Array<ChatCompletionContentPartImage> =
      imageBase64Array.map((base64) => ({
        type: 'image_url',
        image_url: { url: `data:image/jpeg;base64,${base64}` },
      }));

    const messages: ChatCompletionMessageParam[] = [
      {
        role: 'user',
        content: [
          {
            type: 'text',
            text: user_query,
          },
          ...completions,
        ],
      },
    ];

    const startTime = Date.now();

    const chatCompletionFromBase64 = await this.client.chat.completions.create({
      messages,
      model: this.model,
      ...this.defaultParams(),
    });

    const result = chatCompletionFromBase64.choices[0].message.content;
    const endTime = Date.now();
    const timeTaken = (endTime - startTime) / 1000;
    console.log(`Time taken to run the code: ${timeTaken.toFixed(2)} seconds`);
    console.log('Chat completion output for run_multi_image:', result);
  }
}
