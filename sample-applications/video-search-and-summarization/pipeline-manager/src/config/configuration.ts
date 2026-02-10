// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { CONFIG_STATE } from 'src/features/features.model';

export default () => ({
  features: {
    summary: process.env.SUMMARY_FEATURE,
    search: process.env.SEARCH_FEATURE,
  },
  datastore: {
    baseUrl: 'http://datastore:9009',
    host: process.env.MINIO_HOST,
    protocol: process.env.MINIO_PROTOCOL,
    port: process.env.MINIO_PORT,
    accessKey: process.env.MINIO_ROOT_USER,
    secretKey: process.env.MINIO_ROOT_PASSWORD,
    bucketName: process.env.MINIO_BUCKET,
    maxFileSize: process.env.MAX_FILE_SIZE ?? 1_000_000_000,
  },
  search: {
    endpoint: process.env.SEARCH_ENDPOINT,
    dataPrep: process.env.SEARCH_DATAPREP_ENDPOINT,
    dataPrepTimeoutMs: process.env.SEARCH_DATAPREP_TIMEOUT_MS
      ? Number(process.env.SEARCH_DATAPREP_TIMEOUT_MS)
      : 30000,
  },
  database: {
    host: process.env.DB_HOST,
    port: process.env.DB_PORT,
    username: process.env.DB_USER,
    password: process.env.DB_PASSWORD,
    database: process.env.DB_NAME,
  },
  proxy: {
    noProxy: process.env.no_proxy,
    url: process.env.proxy ?? 'http://proxy.example.com:8080',
  },
  evam: {
    host: process.env.EVAM_HOST,
    pipelinePort: process.env.EVAM_PIPELINE_PORT,
    publishPort: process.env.EVAM_PUBLISH_PORT,
    videoTopic: 'topic/video_stream',
    datetimeFormat: 'yyyy_MM_dd-HH_mm_ss.S',
    model: 'yolov8l-worldv2',
    modelPath:
      '/home/pipeline-server/models/yoloworld/v2/FP32/yolov8l-worldv2.xml',
    device: process.env.EVAM_DEVICE ?? 'CPU',
    rmq: {
      queue: 'my_mqtt_queue',
      exchange: 'amq.topic',
    },
  },

  audio: {
    host: process.env.AUDIO_HOST,
    device: process.env.AUDIO_DEVICE,
    version: 'api/v1',
    apiHealth: 'health',
    apiTranscription: 'transcriptions',
    apiModels: 'models',
  },

  rmq: {
    host: process.env.RABBITMQ_HOST,
    amqpPort: process.env.RABBITMQ_AMQP_PORT,
    username: process.env.RABBITMQ_USER,
    password: process.env.RABBITMQ_PASSWORD,
  },

  openai: {
    usecase: 'default',
    useOVMS: process.env.USE_OVMS ?? CONFIG_STATE.OFF,
    llmSummarization: {
      apiKey: process.env.LLM_SUMMARIZATION_KEY ?? '',
      apiBase: process.env.LLM_SUMMARIZATION_API,
      maxContextLength: process.env.MAX_CONTEXT_LENGTH ?? 90_000,
      device: process.env.LLM_SUMMARIZATION_DEVICE,
      concurrent: process.env.LLM_CONCURRENT,
      modelsAPI: process.env.LLM_MODEL_API ?? 'v1/models',
      defaults: {
        temperature: null,
        topP: null,
        presencePenalty: null,
        maxCompletionTokens: process.env.SUMMARIZATION_MAX_COMPLETION_TOKENS,
        frequencyPenalty: null,
        doSample: false,
        seed: 42,
      },
    },
    vlmCaptioning: {
      apiKey: process.env.VLM_CAPTIONING_KEY ?? '',
      apiBase: process.env.VLM_CAPTIONING_API,
      device: process.env.VLM_CAPTIONING_DEVICE,
      concurrent: process.env.VLM_CONCURRENT,
      modelsAPI: process.env.VLM_MODEL_API ?? 'v1/models',
      multiFrame: process.env.MULTI_FRAME_COUNT ?? 12, // process.env.MULTI_FRAME_COUNT ?? 5,
      frameOverlap: 0, // process.env.FRAME_OVERFLAP ?? 0,
      defaults: {
        temperature: 0.1,
        topP: null,
        presencePenalty: null,
        maxCompletionTokens: process.env.CAPTIONING_MAX_COMPLETION_TOKENS,
        frequencyPenalty: 1.0,
        doSample: false,
        seed: 42,
      },
    },
  },
});
