// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Accordion, AccordionItem, Tag } from '@carbon/react';
import Chart from 'chart.js/auto';
import { useEffect, useRef, useState, type JSX } from 'react';
import styled from 'styled-components';

const PanelWrapper = styled.div`
  width: 100%;
  padding: 0 1rem 1.5rem;

  .cds--accordion__item,
  .cds--accordion__content {
    padding-left: 0;
    padding-right: 0;
  }
`;

const StatusRow = styled.div`
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin: 0.75rem 0 1rem;
`;

const MetricLabel = styled.div`
  font-size: 0.9rem;
  color: #6f6f6f;
  font-weight: 600;
`;

const MetricValue = styled.div`
  font-size: 2rem;
  font-weight: 700;
  color: #161616;
`;

const MetricChartGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(18rem, 1fr));
  gap: 1rem;
`;

const MetricChartCard = styled.div`
  background: #ffffff;
  border: 1px solid #d9d9d9;
  border-radius: 0.5rem;
  padding: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
`;

const ScrollBody = styled.div`
  max-height: 60vh;
  overflow-y: auto;
  padding-right: 0.5rem;
`;

const StatusDot = styled.span<{ $active: boolean }>`
  display: inline-block;
  width: 0.65rem;
  height: 0.65rem;
  border-radius: 50%;
  background: ${(props) => (props.$active ? '#0ba35a' : '#da1e28')};
`;

const DetailLine = styled.div`
  font-size: 0.85rem;
  color: #525252;
`;

const MAX_POINTS = 60;
const METRICS_HEALTH_URL = '/metrics-manager/health';
const METRICS_STREAM_URL = '/metrics-manager/metrics/stream';
const STALE_AFTER_MS = 15_000;
const GPU_COLORS = ['#ff832b', '#8a3ffc', '#007d79', '#d12771', '#198038', '#002d9c'];

const getGpuColor = (gpuId: string): string => {
  const numericId = Number.parseInt(gpuId, 10);
  if (Number.isFinite(numericId)) {
    return GPU_COLORS[Math.abs(numericId) % GPU_COLORS.length];
  }

  const hash = Array.from(gpuId).reduce((total, character) => total + character.charCodeAt(0), 0);
  return GPU_COLORS[hash % GPU_COLORS.length];
};

export type MetricState = {
  cpu: number | null;
  ram: number | null;
  gpu: number | null;
  npu: number | null;
  embeddingsPerSecond?: number | null;
  gpus?: Record<string, number>;
};

const formatNumber = (value: number | null | undefined): string => {
  if (value === null || value === undefined || Number.isNaN(value)) return '-';
  return `${value.toFixed(1)}%`;
};

const sanitizeMetricKey = (value: unknown): string | null => {
  if (typeof value !== 'string') return null;
  const normalized = value.trim().toUpperCase();
  if (!normalized) return null;
  if (normalized === '__PROTO__' || normalized === 'CONSTRUCTOR' || normalized === 'PROTOTYPE') {
    return null;
  }
  if (!/^[A-Z0-9_-]{1,32}$/.test(normalized)) {
    return null;
  }
  return normalized;
};

const sanitizeGpuId = (value: unknown): string => {
  if (typeof value !== 'string') return '0';
  const normalized = value.trim();
  return /^[A-Za-z0-9_.-]{1,32}$/.test(normalized) ? normalized : '0';
};

type StreamMetric = {
  name?: unknown;
  labels?: unknown;
  value?: unknown;
};

export const extractMetricState = (payload: unknown): Partial<MetricState> => {
  const metricsArray = Array.isArray(payload) ? payload : (payload as { metrics?: unknown } | null)?.metrics;
  if (!Array.isArray(metricsArray)) return {};

  const next: Partial<MetricState> = {};
  const gpuEngineUsage: Record<string, Record<string, number>> = Object.create(null) as Record<
    string,
    Record<string, number>
  >;

  metricsArray.forEach((rawMetric: StreamMetric) => {
    if (!rawMetric || typeof rawMetric !== 'object') return;
    const name = typeof rawMetric.name === 'string' ? rawMetric.name : '';
    const labels =
      rawMetric.labels && typeof rawMetric.labels === 'object' ? (rawMetric.labels as Record<string, unknown>) : {};
    const value = rawMetric.value;
    if (typeof value !== 'number' || !Number.isFinite(value)) return;

    switch (name) {
      case 'cpu_usage_user':
        next.cpu = value;
        break;
      case 'mem_used_percent':
        next.ram = value;
        break;
      case 'gpu_engine_usage_usage': {
        const safeEngineKey = sanitizeMetricKey(labels.engine);
        if (safeEngineKey) {
          const gpuId = sanitizeGpuId(labels.gpu_id);
          const engines = gpuEngineUsage[gpuId] ?? (Object.create(null) as Record<string, number>);
          engines[safeEngineKey] = value;
          gpuEngineUsage[gpuId] = engines;
        }
        break;
      }
      case 'npu_utilization':
        next.npu = value;
        break;
      case 'dataprep_embeddings_per_second':
      case 'dataprep_embeddings_per_second_value':
        next.embeddingsPerSecond = value;
        break;
      default:
        break;
    }
  });

  const gpuUsage = Object.fromEntries(
    Object.entries(gpuEngineUsage).map(([gpuId, engines]) => [gpuId, Math.max(...Object.values(engines))]),
  );
  if (Object.keys(gpuUsage).length > 0) {
    next.gpu = Math.max(...Object.values(gpuUsage));
    next.gpus = gpuUsage;
  }

  return next;
};

const TelemetryAccordion = (): JSX.Element | null => {
  const [isOpen, setIsOpen] = useState(false);
  const [streamConnected, setStreamConnected] = useState(false);
  const [telemetryAvailable, setTelemetryAvailable] = useState(false);
  const [statusChecked, setStatusChecked] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [isStale, setIsStale] = useState(false);
  const [metrics, setMetrics] = useState<MetricState>({
    cpu: null,
    ram: null,
    gpu: null,
    npu: null,
  });

  const cpuCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const ramCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const gpuCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const npuCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const epsCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const chartsRef = useRef<{
    cpu?: Chart;
    ram?: Chart;
    gpu?: Chart;
    npu?: Chart;
    embeddings?: Chart;
  }>({});

  useEffect(() => {
    let cancelled = false;

    const checkStatus = async () => {
      try {
        const res = await fetch(METRICS_HEALTH_URL);
        if (!res.ok) throw new Error(`Status request failed with ${res.status}`);
        if (cancelled) return;
        setTelemetryAvailable(true);
      } catch (err) {
        if (!cancelled) {
          console.warn('Metrics Manager health check failed', err);
          setTelemetryAvailable(false);
          setStreamConnected(false);
        }
      } finally {
        if (!cancelled) {
          setStatusChecked(true);
        }
      }
    };

    checkStatus();
    const timer = window.setInterval(checkStatus, 15000);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setIsStale(lastUpdated !== null && Date.now() - lastUpdated.getTime() > STALE_AFTER_MS);
    }, 5000);
    return () => window.clearInterval(timer);
  }, [lastUpdated]);

  useEffect(() => {
    if (!isOpen || !telemetryAvailable) {
      return undefined;
    }

    const createChart = (canvas: HTMLCanvasElement | null, label: string, color: string, maxValue = 100) => {
      if (!canvas) return undefined;
      const ctx = canvas.getContext('2d');
      if (!ctx) return undefined;
      const gradient = ctx.createLinearGradient(0, 0, 0, 140);
      gradient.addColorStop(0, `${color}55`);
      gradient.addColorStop(1, `${color}0f`);
      return new Chart(ctx, {
        type: 'line',
        data: {
          labels: [],
          datasets: [
            {
              label,
              data: [],
              borderColor: color,
              backgroundColor: gradient,
              tension: 0.35,
              fill: true,
              pointRadius: 0,
              borderWidth: 2,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: false,
          scales: {
            x: { display: false },
            y: {
              suggestedMin: 0,
              suggestedMax: maxValue,
              grid: { color: 'rgba(0,0,0,0.08)' },
              ticks: { color: '#4c4c4c' },
            },
          },
          plugins: { legend: { display: false } },
        },
      });
    };

    chartsRef.current.cpu = createChart(cpuCanvasRef.current, 'CPU %', '#0f62fe');
    chartsRef.current.ram = createChart(ramCanvasRef.current, 'RAM %', '#8ca0c2');
    chartsRef.current.gpu = createChart(gpuCanvasRef.current, 'GPU %', '#ff832b');
    if (chartsRef.current.gpu) {
      chartsRef.current.gpu.data.datasets = [];
      if (chartsRef.current.gpu.options.plugins?.legend) {
        chartsRef.current.gpu.options.plugins.legend.display = true;
      }
    }
    chartsRef.current.npu = createChart(npuCanvasRef.current, 'NPU %', '#a56eff');
    chartsRef.current.embeddings = createChart(epsCanvasRef.current, 'Embeddings/sec', '#3ddbd9', 50);

    return () => {
      chartsRef.current.cpu?.destroy();
      chartsRef.current.ram?.destroy();
      chartsRef.current.gpu?.destroy();
      chartsRef.current.npu?.destroy();
      chartsRef.current.embeddings?.destroy();
      chartsRef.current = {};
    };
  }, [isOpen, telemetryAvailable]);

  useEffect(() => {
    if (!isOpen || !telemetryAvailable) return undefined;

    const pushSample = (chart: Chart | undefined, value: number | null | undefined) => {
      if (!chart || value === null || value === undefined || Number.isNaN(value)) return;
      const labels = chart.data.labels ?? [];
      const dataset = chart.data.datasets?.[0];
      if (!dataset) return;
      labels.push(new Date().toLocaleTimeString());
      (dataset.data as number[]).push(value);
      if (labels.length > MAX_POINTS) {
        labels.shift();
        (dataset.data as number[]).shift();
      }
      chart.update('none');
    };

    const pushGpuSamples = (chart: Chart | undefined, gpuValues: Record<string, number> | undefined) => {
      if (!chart || !gpuValues || Object.keys(gpuValues).length === 0) return;

      const labels = chart.data.labels ?? [];
      labels.push(new Date().toLocaleTimeString());

      chart.data.datasets.forEach((dataset) => {
        dataset.data.push(null);
      });

      Object.entries(gpuValues)
        .sort(([left], [right]) => left.localeCompare(right, undefined, { numeric: true }))
        .forEach(([gpuId, value]) => {
          const label = `GPU ${gpuId}`;
          let dataset = chart.data.datasets.find((candidate) => candidate.label === label);
          if (!dataset) {
            const color = getGpuColor(gpuId);
            dataset = {
              label,
              data: Array(labels.length).fill(null),
              borderColor: color,
              backgroundColor: color,
              tension: 0.35,
              fill: false,
              pointRadius: 0,
              borderWidth: 2,
            };
            chart.data.datasets.push(dataset);
          }
          dataset.data[dataset.data.length - 1] = value;
        });

      if (labels.length > MAX_POINTS) {
        labels.shift();
        chart.data.datasets.forEach((dataset) => dataset.data.shift());
      }
      chart.update('none');
    };

    const processMetrics = (payload: unknown) => {
      const next = extractMetricState(payload);
      pushSample(chartsRef.current.cpu, next.cpu);
      pushSample(chartsRef.current.ram, next.ram);
      pushGpuSamples(chartsRef.current.gpu, next.gpus);
      pushSample(chartsRef.current.npu, next.npu);
      pushSample(chartsRef.current.embeddings, next.embeddingsPerSecond);
      setMetrics((prev) => ({ ...prev, ...next }));
      setLastUpdated(new Date());
      setIsStale(false);
    };

    const source = new EventSource(METRICS_STREAM_URL);
    source.onopen = () => {
      setStreamConnected(true);
      setTelemetryAvailable(true);
    };
    source.onmessage = (event) => {
      try {
        const data: unknown = JSON.parse(event.data);
        if (data && typeof data === 'object' && 'error' in data) {
          setStreamConnected(false);
          return;
        }
        processMetrics(data);
      } catch (err) {
        console.error('Metrics Manager SSE parse error', err);
      }
    };
    source.onerror = () => {
      setStreamConnected(false);
    };

    return () => {
      source.close();
    };
  }, [isOpen, telemetryAvailable]);

  if (!statusChecked || !telemetryAvailable) {
    return null;
  }

  return (
    <PanelWrapper>
      <Accordion align='start' size='sm'>
        {/* Default collapsed */}
        <AccordionItem title='System telemetry' open={isOpen} onHeadingClick={() => setIsOpen((prev) => !prev)}>
          <ScrollBody>
            <StatusRow>
              <StatusDot $active={streamConnected && !isStale} />
              <div>
                {streamConnected
                  ? isStale
                    ? 'Metrics stream stale'
                    : 'Metrics Manager connected'
                  : 'Metrics Manager reconnecting'}
              </div>
              {lastUpdated && (
                <Tag size='sm' type='cool-gray'>
                  Updated {lastUpdated.toLocaleTimeString()}
                </Tag>
              )}
            </StatusRow>

            <MetricChartGrid>
              <MetricChartCard>
                <MetricLabel>Embeddings / sec</MetricLabel>
                <MetricValue>
                  {metrics.embeddingsPerSecond !== undefined && metrics.embeddingsPerSecond !== null
                    ? metrics.embeddingsPerSecond.toFixed(1)
                    : '-'}
                </MetricValue>
                <div style={{ height: '180px' }}>
                  <canvas ref={epsCanvasRef} aria-label='embeddings-chart'></canvas>
                </div>
              </MetricChartCard>

              <MetricChartCard>
                <MetricLabel>CPU Usage</MetricLabel>
                <MetricValue>{formatNumber(metrics.cpu)}</MetricValue>
                <div style={{ height: '180px' }}>
                  <canvas ref={cpuCanvasRef} aria-label='cpu-chart'></canvas>
                </div>
              </MetricChartCard>

              <MetricChartCard>
                <MetricLabel>RAM Usage</MetricLabel>
                <MetricValue>{formatNumber(metrics.ram)}</MetricValue>
                <div style={{ height: '180px' }}>
                  <canvas ref={ramCanvasRef} aria-label='ram-chart'></canvas>
                </div>
              </MetricChartCard>

              <MetricChartCard>
                <MetricLabel>GPU Usage</MetricLabel>
                <MetricValue>{formatNumber(metrics.gpu)}</MetricValue>
                <div style={{ height: '180px' }}>
                  <canvas ref={gpuCanvasRef} aria-label='gpu-chart'></canvas>
                </div>
              </MetricChartCard>

              <MetricChartCard>
                <MetricLabel>NPU Usage</MetricLabel>
                <MetricValue>{formatNumber(metrics.npu)}</MetricValue>
                <div style={{ height: '180px' }}>
                  <canvas ref={npuCanvasRef} aria-label='npu-chart'></canvas>
                </div>
              </MetricChartCard>
            </MetricChartGrid>

            <DetailLine style={{ marginTop: '0.75rem' }}>Metrics sourced directly from Metrics Manager.</DetailLine>
          </ScrollBody>
        </AccordionItem>
      </Accordion>
    </PanelWrapper>
  );
};

export default TelemetryAccordion;
