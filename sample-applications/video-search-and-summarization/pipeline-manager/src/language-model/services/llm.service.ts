// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import {
  Injectable,
  Logger,
  ServiceUnavailableException,
} from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { HttpsProxyAgent } from 'https-proxy-agent';
import { OpenAI } from 'openai';
import { APIPromise } from 'openai/core';
import { ChatCompletion, ChatCompletionChunk } from 'openai/resources';
import { Stream } from 'openai/streaming';
import { firstValueFrom, from, map, Observable, Subject } from 'rxjs';
import { ModelInfo } from 'src/state-manager/models/state.model';
import { CompletionQueryParams } from '../models/completion.model';
import { TemplateService } from './template.service';
import { OpenaiHelperService } from './openai-helper.service';
import { FeaturesService } from 'src/features/features.service';
import { CONFIG_STATE } from 'src/features/features.model';
import { InferenceCountService } from './inference-count.service';

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
export class LlmService {
  public client: OpenAI;
  public model: string;
  public serviceReady: boolean = false;

  constructor(
    private $config: ConfigService,
    private $feature: FeaturesService,
    private $template: TemplateService,
    private $openAiHelper: OpenaiHelperService,
    private $inferenceCount: InferenceCountService,
  ) {
    if (this.$feature.hasFeature('summary')) {
      this.initialize().catch((error) => {
        console.error('LlmService initialization failed:');
        throw error;
      });
    }
  }

  public getInferenceConfig(): ModelInfo {
    const device: string = this.$config.get<string>(
      'openai.llmSummarization.device',
    )!;
    return { device, model: this.model };
  }

  private defaultParams(): CompletionQueryParams {
    const accessKey = ['openai', 'llmSummarization', 'defaults'].join('.');
    const params: CompletionQueryParams = {};

    if (this.$config.get(`${accessKey}.doSample`) !== null) {
      params.do_sample = this.$config.get(`${accessKey}.doSample`)!;
    }
    if (this.$config.get(`${accessKey}.seed`) !== null) {
      params.seed = +this.$config.get(`${accessKey}.seed`)!;
    }
    if (this.$config.get(`${accessKey}.temperature`) !== null) {
      params.temperature = +this.$config.get(`${accessKey}.temperature`)!;
    }
    if (this.$config.get(`${accessKey}.topP`) !== null) {
      params.top_p = +this.$config.get(`${accessKey}.topP`)!;
    }
    if (this.$config.get(`${accessKey}.presencePenalty`) !== null) {
      params.presence_penalty = +this.$config.get(
        `${accessKey}.presencePenalty`,
      )!;
    }
    if (this.$config.get(`${accessKey}.frequencyPenalty`) !== null) {
      params.frequency_penalty = +this.$config.get(
        `${accessKey}.frequencyPenalty`,
      )!;
    }
    if (this.$config.get(`${accessKey}.maxCompletionTokens`) !== null) {
      params.max_completion_tokens = +this.$config.get(
        `${accessKey}.maxCompletionTokens`,
      )!;
      params.max_tokens = +this.$config.get(
        `${accessKey}.maxCompletionTokens`,
      )!;
    }

    return params;
  }

  private async initialize() {
    let configUrl: string | null = null;
    const fetchOptions: { agent?: HttpsProxyAgent<string> } = {};
    const apiKey = this.$config.get<string>('openai.llmSummarization.apiKey')!;
    const baseURL = this.$config.get<string>(
      'openai.llmSummarization.apiBase',
    )!;
    const usingOVMS = this.$config.get<string>('openai.useOVMS');
    try {
      const { client, openAiConfig, proxyAgent } =
        this.$openAiHelper.initializeClient(apiKey, baseURL);

      this.client = client;

      if (proxyAgent) {
        fetchOptions.agent = proxyAgent;
      }
      const modelsApi = this.$config.get<string>(
        'openai.llmSummarization.modelsAPI',
      )!;

      configUrl = this.$openAiHelper.getConfigUrl(openAiConfig, modelsApi);
    } catch (error) {
      console.error('Failed to initialize OpenAI client:', error);
      throw error;
    }

    try {
      if (usingOVMS === CONFIG_STATE.ON && configUrl) {
        await this.fetchModelsFromConfig(configUrl, fetchOptions);
        this.serviceReady = true;
        this.$inferenceCount.setLlmConfig({
          model: this.model,
          ip: baseURL,
        });
      } else {
        throw new Error('Config URL is not available');
      }
    } catch (error) {
      Logger.error(error);

      try {
        if (!this.client) {
          throw new Error('Client is not initialized');
        }
        await this.fetchModelsFromOpenai();
        this.serviceReady = true;
        this.$inferenceCount.setLlmConfig({
          model: this.model,
          ip: baseURL,
        });
      } catch (error) {
        Logger.error(error);
        throw new ServiceUnavailableException('Open AI fetch models failed');
      }
    }
  }

  private async fetchModelsFromConfig(url: string, fetchOptions) {
    const response = await fetch(url, fetchOptions as RequestInit);
    if (response.ok) {
      const data: ModelConfigResponse =
        (await response.json()) as ModelConfigResponse;
      const modelKey = Object.keys(data)[0];
      if (data[modelKey].model_version_status[0].state === 'AVAILABLE') {
        this.model = modelKey;
        console.log(`Using LLM model: ${this.model}`);
      } else {
        console.warn(
          `model: ${modelKey} is in ${data[modelKey].model_version_status[0].state} state`,
        );
        this.model = modelKey;
      }
    } else {
      throw new Error(`Failed to retrieve model from endpoint: ${url}`);
    }
  }

  private async fetchModelsFromOpenai() {
    if (this.client) {
      const models = await this.client.models.list();
      console.log('Models', models);
      if (models.data && models.data.length > 0) {
        this.model = models.data[0].id;
        console.log(`Using model: ${this.model}`);
      } else {
        throw new Error('No models available');
      }
    }
  }

  public async summarizeMapReduce(
    texts: string[],
    summarizeTemplate: string,
    reduceTemplate: string,
    reduceSingleTextTemplate: string,
    streamer: Subject<string>,
  ) {
    const maxContextLength = this.$config.get<number>(
      'openai.llmSummarization.maxContextLength',
      100000,
    );
    const concurrent = this.$config.get<number>(
      'openai.llmSummarization.concurrent',
      4,
    );

    const summarizeBatch = async (
      batch: string[],
      promptTemplate: string,
      stream: boolean = false,
    ) => {
      const prompt = this.$template.createUserQuery(promptTemplate, batch);
      console.log('summarizeBatch prompt: ', prompt);
      if (stream) {
        return this.generateStreamingResponse(prompt, streamer);
      }
      return (await firstValueFrom(this.generateResponse(prompt))) as string;
    };

    const createBatches = async (
      texts: string[],
      maxLength: number,
      tempTemplate: string = '',
    ): Promise<string[][]> => {
      const batches: string[][] = [];
      let batch: string[] = [];
      let batchLength = 0;
      console.log('texts:', texts);
      for (let text of texts) {
        if (batchLength + text.length + tempTemplate.length > maxLength) {
          console.log('text len > maxLength');
          if (batch.length < 2) {
            console.log('batch len < 2');
            // For it to reduce, min 2 texts should go in one batch. So lets maintain len of a batch >= 2
            let attempts = 0;
            const maxAttempts = 3;
            while (
              batchLength + text.length + tempTemplate.length >
              maxLength
            ) {
              console.log(
                `Attempt ${attempts} reducing text to create batch. 
                text: ${text},
                batch[0]: ${batch[0] ? batch[0] : null}`,
              );
              if (attempts >= maxAttempts) {
                throw new Error(
                  `Context length of '${maxLength}' for model '${this.model}' is too small to run map-reduce chain on given inputs of length '${batchLength + text.length}'`,
                );
              }
              if (batch.length === 0) {
                // If Single text is exceeding maxLength only reduce that
                const reducedText = await firstValueFrom(
                  this.generateResponse(
                    this.$template.createUserQuery(
                      reduceSingleTextTemplate,
                      text,
                    ),
                  ),
                );
                text = reducedText!;
              } else {
                // If sum of current text and batch[0] is exceeding maxLength then reduce both individually
                const reducedCurrText = await firstValueFrom(
                  this.generateResponse(
                    this.$template.createUserQuery(
                      reduceSingleTextTemplate,
                      text,
                    ),
                  ),
                );
                const reducedBatchText = await firstValueFrom(
                  this.generateResponse(
                    this.$template.createUserQuery(
                      reduceSingleTextTemplate,
                      batch[0],
                    ),
                  ),
                );
                text = reducedCurrText!;
                batch[0] = reducedBatchText!;
                batchLength = batch[0].length;
              }
              attempts++;
            }
            // when (batchLength + text.length) > maxLength and batch.length < 2
            // inner while loop brings total len to <= maxLength
            // push the curr text to curr batch
            // push the curr batch to batches
            // clear the batch for next iteration & set len = 0
            batch.push(text);
            batches.push(batch);
            batch = [];
            batchLength = 0;
          } else {
            // when (batchLength + text.length) > maxLength and batch.length >= 2
            // push curr batch to batches
            // clear batch for next iteration
            // push curr text to new batch & set len to curr text len
            batches.push(batch);
            batch = [];
            batch.push(text);
            batchLength = text.length;
          }
        } else {
          // when (batchLength + text.length) <= maxLength
          // push curr text to curr batch and increment len
          batch.push(text);
          batchLength += text.length;
        }
      }
      if (batch.length > 0) {
        // when for loop exhausts and last batch was not pushed to batches
        batches.push(batch);
      }
      return batches;
    };

    let currentTexts = texts;
    let tempTemplate = summarizeTemplate;
    while (true) {
      // check if length of list texts can be sent in one pass
      const currentLength =
        currentTexts.reduce((acc, text) => acc + text.length, 0) +
        tempTemplate.length;
      console.log('maxContextLength:', maxContextLength);
      console.log('currentLength:', currentLength);
      if (currentLength <= maxContextLength) {
        // final response generated from here
        // if stream == true then send from here
        return summarizeBatch(currentTexts, tempTemplate, true);
        // return finalResponse as AsyncGenerator<string, void, unknown>;
      }
      // create array of arrays containing batch of texts where each batch length can be sent in one pass
      const batches: string[][] = await createBatches(
        currentTexts,
        maxContextLength,
        tempTemplate,
      );
      const summaries: string[] = [];

      for (let i = 0; i < batches.length; i += concurrent) {
        const batchSlice = batches.slice(i, i + concurrent);
        const batchPromises = batchSlice.map((batch) =>
          summarizeBatch(batch, tempTemplate),
        );
        const batchSummaries = await Promise.all(batchPromises);
        summaries.push(...(batchSummaries as unknown as string));
      }

      // Modify for while loop the next iteration of currentTexts and change prompt to reduce prompt to create summary of summaries
      currentTexts = summaries;
      tempTemplate = reduceTemplate;
    }
  }

  private getChatCompletions(userQuery: string, stream: boolean) {
    return this.client.chat.completions.create({
      messages: [{ role: 'user', content: userQuery }],
      model: this.model,
      ...this.defaultParams(),
      stream,
    });
  }

  generateResponse(userQuery: string): Observable<string | null> {
    const stream = false;

    const chatCompletions = this.getChatCompletions(
      userQuery,
      stream,
    ) as APIPromise<ChatCompletion>;

    return from(chatCompletions).pipe(
      map((res) => res.choices[0].message.content ?? null),
    );
  }

  async generateStreamingResponse(
    userQuery: string,
    streamer: Subject<string>,
  ) {
    const stream = true;

    const completionQuery = await (this.getChatCompletions(
      userQuery,
      stream,
    ) as APIPromise<Stream<ChatCompletionChunk>>);

    for await (const chunk of completionQuery) {
      if (chunk.choices && chunk.choices.length > 0) {
        const content = chunk.choices[0].delta.content;
        if (content) {
          streamer.next(content);
        }
      }
    }

    streamer.complete();

    return completionQuery;
  }

  public async runTextOnlyInference(
    user_query: string,
    stream: boolean = false,
  ): Promise<string | AsyncGenerator<string, void, unknown> | null> {
    const startTime = Date.now();

    if (stream) {
      const chatCompletion = await this.client.chat.completions.create({
        messages: [
          {
            role: 'user',
            content: user_query,
          },
        ],
        model: this.model,
        ...this.defaultParams(),
        stream: true,
      });

      async function* streamGenerator() {
        for await (const chunk of chatCompletion) {
          if (chunk.choices && chunk.choices.length > 0) {
            const content = chunk.choices[0].delta?.content;
            if (content) {
              yield content;
            }
          }
        }
      }

      return streamGenerator();
    } else {
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
      console.log(
        `Time taken to run the code: ${timeTaken.toFixed(2)} seconds`,
      );
      console.log('Chat completion output:', result);
      return result;
    }
  }
}
