// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { getNodeAutoInstrumentations } from '@opentelemetry/auto-instrumentations-node';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { NodeSDK } from '@opentelemetry/sdk-node';
import { ConsoleSpanExporter } from '@opentelemetry/sdk-trace-base';

const otelSDK = new NodeSDK({
  serviceName: 'videoSummary',
  traceExporter: process.env.OTLP_TRACE_URL
    ? new OTLPTraceExporter({ url: process.env.OTLP_TRACE_URL })
    : new ConsoleSpanExporter(),
  instrumentations: [getNodeAutoInstrumentations()],
});

export default otelSDK;

process.on('SIGTERM', () => {
  otelSDK
    .shutdown()
    .then(
      () => console.log('SDK shut down successfully'),
      (err) => console.log('Error shutting down SDK', err),
    )
    .finally(() => process.exit(0));
});
