// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

export const USE_MONITOR_MOCK_DATA = true;

export const tokenSavingMockData = {
  token_metrics: {
    local_model: {
      input_tokens: 12840,
      output_tokens: 4260,
      total_tokens: 17100,
    },
    cloud_model: {
      input_tokens: 64200,
      output_tokens: 15880,
      total_tokens: 80080,
    },
    overall: {
      total_tokens: 97180,
    },
  },
  compression: {
    total_input: {
      original_tokens: 118600,
      compressed_tokens: 64200,
      save_pct: 45.9,
      rest_pct: 54.1,
    },
    system_and_tools: {
      original_tokens: 23600,
      compressed_tokens: 12840,
      save_pct: 45.6,
      rest_pct: 54.4,
    },
  },
};

export const routerApiMockData = {
  health: {
    status: "healthy",
    router: "initialized",
    concurrency: { active_requests: 0, max_concurrency: 3 },
  },
  metrics: {
    routing_stats: {
      total_requests: 12,
      by_provider: {
        "Qwen/Qwen3-8B@local": 8,
        "MiniMax-M2.7@cloud": 4,
        "MiniMax-M2.7@cloud2": 4,
      },
    },
    token_metrics: {
      overall: {
        total_tokens: 420000,
        total_input_tokens: 240000,
        total_output_tokens: 180000,
        total_requests: 16,
        avg_tokens_per_request: 266.7,
      },
      before_router: {
        system_prompt_tokens: 60000,
        tool_schema_tokens: 100000,
        context_tokens: 53000,
        overall_tokens: 59000,
      },
      after_router: {
        system_prompt_tokens: 20000,
        tool_schema_tokens: 40000,
        context_tokens: 20000,
        overall_tokens: 30000,
      },
      by_provider: {
        "Qwen/Qwen3.5-9B@local": {
          input_tokens: 120000,
          output_tokens: 80000,
          total_tokens: 200000,
          request_count: 8,
          avg_tokens_per_request: 250.0,
          request_share: 0.5,
          token_share: 0.476,
        },
        "MiniMax-M2.7@cloud": {
          input_tokens: 70000,
          output_tokens: 50000,
          total_tokens: 120000,
          request_count: 4,
          avg_tokens_per_request: 250.0,
          request_share: 0.25,
          token_share: 0.286,
        },
        "MiniMax-M2.7@cloud2": {
          input_tokens: 50000,
          output_tokens: 50000,
          total_tokens: 100000,
          request_count: 4,
          avg_tokens_per_request: 100.0,
          request_share: 0.25,
          token_share: 0.238,
        },
      },
    },
    latency_metrics: {
      overall: {
        avg_latency_ms: 510.4,
        avg_ttft_ms: 38.1,
        avg_tpot_ms: 5.1042,
        ttft_count: 7,
        tpot_count: 7,
      },
      by_provider: {
        "Qwen/Qwen3.5-9B@local": {
          avg_latency_ms: 420.15,
          avg_ttft_ms: 351.2,
          avg_tpot_ms: 41.8123,
          ttft_count: 5,
          tpot_count: 5,
        },
        "MiniMax-M2.7@cloud": {
          avg_latency_ms: 420.15,
          avg_ttft_ms: 352.2,
          avg_tpot_ms: 43.8123,
          ttft_count: 5,
          tpot_count: 5,
        },
        "MiniMax-M2.7@cloud2": {
          avg_latency_ms: 430.15,
          avg_ttft_ms: 157.2,
          avg_tpot_ms: 84.8123,
          ttft_count: 5,
          tpot_count: 5,
        },
      },
    },
  },
  providers: {
    data: [
      {
        name: "local",
        type: "hosted_vllm",
        model: "Qwen/Qwen3-8B",
        enabled: true,
      },
      { name: "cloud", type: "openai", model: "MiniMax-M2.7", enabled: false },
    ],
  },
  models: {
    data: [
      { id: "Qwen/Qwen3-8B", owned_by: "local" },
      { id: "MiniMax-M2.7", owned_by: "cloud" },
      { id: "auto", owned_by: "inference-router" },
    ],
  },
  config: {
    data: {
      providers: [
        {
          name: "local",
          type: "openai",
          model: "Qwen/Qwen3-8B",
          enabled: true,
          metadata: {},
          settings: { api_key: "***REDACTED***" },
        },
        {
          name: "cloud",
          type: "openai",
          model: "MiniMax-M2.7",
          enabled: false,
          metadata: { labels: ["cloud"] },
          settings: {
            api_key: "***REDACTED***",
            endpoint: "https://api.example.com/v1",
          },
        },
      ],
      routing: { policy: "default", strategy: "auto" },
      telemetry: { enabled: true },
      plugins: { prerouting: [], postrouting: [], postresponse: [] },
    },
  },
} as const;
