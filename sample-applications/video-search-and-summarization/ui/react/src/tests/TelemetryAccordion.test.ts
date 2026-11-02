// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { describe, expect, it } from 'vitest';
import { extractMetricState } from '../components/Search/TelemetryAccordion';

describe('extractMetricState', () => {
  it('maps Metrics Manager SSE names to UI state', () => {
    const state = extractMetricState({
      metrics: [
        { name: 'cpu_usage_user', labels: { cpu: 'cpu-total' }, value: 12.5 },
        { name: 'mem_used_percent', labels: {}, value: 45.25 },
        {
          name: 'gpu_engine_usage_usage',
          labels: { engine: 'compute', gpu_id: '0' },
          value: 71,
        },
        { name: 'npu_utilization', labels: {}, value: 33 },
        { name: 'dataprep_embeddings_per_second', labels: {}, value: 9.5 },
      ],
    });

    expect(state).toMatchObject({
      cpu: 12.5,
      ram: 45.25,
      gpu: 71,
      npu: 33,
      embeddingsPerSecond: 9.5,
      gpus: { 0: 71 },
    });
  });

  it('keeps utilization for multiple GPUs as separate series', () => {
    const state = extractMetricState({
      metrics: [
        {
          name: 'gpu_engine_usage_usage',
          labels: { engine: 'compute', gpu_id: '0' },
          value: 71,
        },
        {
          name: 'gpu_engine_usage_usage',
          labels: { engine: 'render', gpu_id: '0' },
          value: 12,
        },
        {
          name: 'gpu_engine_usage_usage',
          labels: { engine: 'compute', gpu_id: '1' },
          value: 8,
        },
        {
          name: 'gpu_engine_usage_usage',
          labels: { engine: 'render', gpu_id: '1' },
          value: 17,
        },
      ],
    });

    expect(state).toMatchObject({
      gpu: 71,
      gpus: { 0: 71, 1: 17 },
    });
  });

  it('ignores malformed, non-finite, and unsafe engine samples', () => {
    const state = extractMetricState({
      metrics: [
        null,
        { name: 'cpu_usage_user', value: Number.NaN },
        {
          name: 'gpu_engine_usage_usage',
          labels: { engine: '__proto__' },
          value: 10,
        },
        { name: 'npu_utilization', value: 'not-a-number' },
      ],
    });

    expect(state).toEqual({});
  });

  it('accepts the Prometheus value suffix used by some Telegraf versions', () => {
    expect(
      extractMetricState({
        metrics: [{ name: 'dataprep_embeddings_per_second_value', value: 4.25 }],
      }),
    ).toMatchObject({ embeddingsPerSecond: 4.25 });
  });
});
