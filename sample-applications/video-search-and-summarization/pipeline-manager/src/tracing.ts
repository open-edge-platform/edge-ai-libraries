// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { getNodeAutoInstrumentations } from '@opentelemetry/auto-instrumentations-node';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { NodeSDK } from '@opentelemetry/sdk-node';
import {
  ConsoleSpanExporter,
  SpanExporter,
} from '@opentelemetry/sdk-trace-base';

// Select the trace exporter based on environment:
//   - OTLP_TRACE_URL set          -> export spans to the OTLP collector.
//   - OTEL_CONSOLE_EXPORTER=true   -> print spans to stdout (very verbose;
//                                     opt-in for local debugging only).
//   - otherwise                    -> no exporter. Spans are not emitted, so
//                                     container logs stay clean. Previously this
//                                     fell back to ConsoleSpanExporter, which
//                                     dumped every auto-instrumented span
//                                     (HTTP/DB/AMQP) to stdout and flooded the
//                                     container logs.
function resolveTraceExporter(): SpanExporter | undefined {
  if (process.env.OTLP_TRACE_URL) {
    return new OTLPTraceExporter({ url: process.env.OTLP_TRACE_URL });
  }
  if (process.env.OTEL_CONSOLE_EXPORTER === 'true') {
    return new ConsoleSpanExporter();
  }
  return undefined;
}

const traceExporter = resolveTraceExporter();

const otelSDK = new NodeSDK({
  serviceName: 'videoSummary',
  // Only attach a span processor when an exporter is configured; without one
  // NodeSDK records no traces and writes nothing to the console.
  ...(traceExporter ? { traceExporter } : {}),
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
