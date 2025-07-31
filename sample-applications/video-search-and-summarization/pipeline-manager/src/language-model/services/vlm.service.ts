// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Injectable, Logger } from '@nestjs/common';
import { OpenAI } from 'openai';
import { ConfigService } from '@nestjs/config';
import {
  ChatCompletionContentPartImage,
  ChatCompletionMessageParam,
} from 'openai/resources';
import { CompletionQueryParams } from '../models/completion.model';
import { TemplateService } from './template.service';
import { ModelInfo } from 'src/state-manager/models/state.model';
import { OpenaiHelperService } from './openai-helper.service';
import { FeaturesService } from 'src/features/features.service';
import { InferenceCountService } from './inference-count.service';

interface ImageCompletionParams extends CompletionQueryParams {
  user_query?: string;
  fileNameOrUrl: string;
}

interface MultiImageCompletionParams extends CompletionQueryParams {
  user_query?: string;
  fileNameOrUrl: string[];
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

    if (this.$config.get(`${accessKey}.doSample`) !== null) {
      params.do_sample = this.$config.get(`${accessKey}.doSample`)!;
    }
    if (this.$config.get(`${accessKey}.seed`) !== null) {
      params.seed = +this.$config.get(`${accessKey}.seed`)!;
    }
    if (this.$config.get(`${accessKey}.temperature`)) {
      params.temperature = +this.$config.get(`${accessKey}.temperature`)!;
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
      params.max_completion_tokens = +this.$config.get(
        `${accessKey}.maxCompletionTokens`,
      )!;
    }

    return params;
  }

  private async initialize() {
    const apiKey: string = this.$config.get<string>(
      'openai.vlmCaptioning.apiKey',
    )!;
    const baseURL: string = this.$config.get<string>(
      'openai.vlmCaptioning.apiBase',
    )!;

    try {
      // Initialize OpenAI Client
      const { client } = this.$openAiHelper.initializeClient(apiKey, baseURL);
      this.client = client;
    } catch (error) {
      console.error('Failed to initialize OpenAI client:', error);
      throw error;
    }

    try {
      // Fetch Models
      await this.getModelsFromOpenai();
      this.serviceReady = true;
      this.$inferenceCount.setVlmConfig({
        model: this.model,
        ip: baseURL,
      });
    } catch (error) {
      console.error('Failed to retrieve models:', error);
    }
  }

  private async getModelsFromOpenai() {
    if (this.client) {
      const models = await this.client.models.list();
      console.log('Models', models);
      if (models.data && models.data.length > 0) {
        this.models = models.data;
        this.model = models.data[0].id;
        console.log(`Using model: ${this.model}`);
      } else {
        throw new Error('No models available');
      }
    }
  }

  private encodeBase64ContentFromUrl(fileNameOrUrl: string): string {
    // TODO: will require fixing when required

    try {
      // const buffer: any[] = await this.$dataStore.getFile(
      //   fileNameOrUrl,
      //   'willFixAsRequired',
      // );
      // return base64.fromByteArray(buffer as any);
      return '';
    } catch (error) {
      throw new Error('Failed to fetch content');
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
      console.log(userQuery, imageUri);

      let content: any[];

      if (imageUri.length === 1) {
        // Single image case
        content = [
          {
            type: 'image_url',
            image_url: { url: imageUri[0] },
          },
        ];
      } else {
        content = [
          {
            type: 'video',
            video: imageUri.map((url) => url),
          },
        ];
      }

      const messages: any[] = [
        {
          role: 'user',
          // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
          content: [{ type: 'text', text: userQuery }, ...content],
        },
      ];

      const completions = await this.client.chat.completions.create({
        // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
        messages,
        model: this.model,
        ...this.defaultParams(),
      });

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

  public async runSingleImage(
    params: ImageCompletionParams,
  ): Promise<string | null> {
    const {
      user_query = this.$template.getFrameCaptionTemplateWithoutObjects(),
      fileNameOrUrl,
    } = params;

    const imageBase64 = this.encodeBase64ContentFromUrl(fileNameOrUrl);
    const startTime = Date.now();
    const chatCompletionFromBase64 = await this.client.chat.completions.create({
      messages: [
        {
          role: 'user',
          content: [
            {
              type: 'text',
              text: user_query,
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

    const result = chatCompletionFromBase64.choices[0].message.content;
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
