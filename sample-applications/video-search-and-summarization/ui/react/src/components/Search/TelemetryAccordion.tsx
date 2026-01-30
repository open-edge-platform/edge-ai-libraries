// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Accordion, AccordionItem, Tag } from '@carbon/react';
import Chart from 'chart.js/auto';
import { useEffect, useMemo, useRef, useState, type JSX } from 'react';
import styled from 'styled-components';
import { APP_URL } from '../../config';

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

const MetricSubtext = styled.div`
  font-size: 0.85rem;
  color: #4c4c4c;
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

type MetricState = {
  cpu: number | null;
  ram: number | null;
  gpu: number | null;
  embeddingsPerSecond?: number | null;
  gpuFreq?: number | null;
  gpuPower?: number | null;
  pkgPower?: number | null;
  gpuEngines?: Record<string, number>;
};

const formatNumber = (value: number | null | undefined): string => {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return `${value.toFixed(1)}%`;
};

const normalizeApiBase = (): string | null => {
  const configured = APP_URL?.trim();
  if (!configured) return null;

  if (configured.startsWith('http')) {
    return configured.replace(/\/$/, '');
  }

  const origin = window.location.origin.replace(/\/$/, '');
  const path = configured.startsWith('/') ? configured : `/${configured}`;
  return `${origin}${path.replace(/\/$/, '')}`;
};

const TelemetryAccordion = (): JSX.Element | null => {
  const [isOpen, setIsOpen] = useState(false);
  const [collectorConnected, setCollectorConnected] = useState(false);
  const [telemetryAvailable, setTelemetryAvailable] = useState(false);
  const [statusChecked, setStatusChecked] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [metrics, setMetrics] = useState<MetricState>({ cpu: null, ram: null, gpu: null });

  const cpuCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const ramCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const gpuCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const epsCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const chartsRef = useRef<{ cpu?: Chart; ram?: Chart; gpu?: Chart; embeddings?: Chart }>({});

  const apiBase = useMemo(() => normalizeApiBase(), []);

  const websocketUrl = useMemo(() => {
    if (!apiBase) return null;
    try {
      const url = new URL(apiBase);
      url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
      url.pathname = `${url.pathname.replace(/\/$/, '')}/metrics/ws/clients`;
      return url.toString();
    } catch (err) {
      console.error('Telemetry websocket URL construction failed', err);
      return null;
    }
  }, [apiBase]);

  const statusUrl = useMemo(() => (apiBase ? `${apiBase}/metrics/status` : null), [apiBase]);

  useEffect(() => {
    if (!statusUrl) return undefined;

    let cancelled = false;

    const checkStatus = async () => {
      try {
        const res = await fetch(statusUrl);
        if (!res.ok) throw new Error(`Status request failed with ${res.status}`);
        const data = await res.json();
        if (cancelled) return;
        const connected = Boolean((data as { collectorConnected?: unknown }).collectorConnected);
        setTelemetryAvailable(connected);
        setCollectorConnected(connected);
      } catch (err) {
        if (!cancelled) {
          console.warn('Telemetry status check failed', err);
          setTelemetryAvailable(false);
          setCollectorConnected(false);
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
  }, [statusUrl]);

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
        data: { labels: [], datasets: [{ label, data: [], borderColor: color, backgroundColor: gradient, tension: 0.35, fill: true, pointRadius: 0, borderWidth: 2 }] },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: false,
          scales: {
            x: { display: false },
            y: { suggestedMin: 0, suggestedMax: maxValue, grid: { color: 'rgba(0,0,0,0.08)' }, ticks: { color: '#4c4c4c' } },
          },
          plugins: { legend: { display: false } },
        },
      });
    };

    chartsRef.current.cpu = createChart(cpuCanvasRef.current, 'CPU %', '#0f62fe');
    chartsRef.current.ram = createChart(ramCanvasRef.current, 'RAM %', '#8ca0c2');
    chartsRef.current.gpu = createChart(gpuCanvasRef.current, 'GPU %', '#ff832b');
    chartsRef.current.embeddings = createChart(epsCanvasRef.current, 'Embeddings/sec', '#3ddbd9', 50);

    return () => {
      chartsRef.current.cpu?.destroy();
      chartsRef.current.ram?.destroy();
      chartsRef.current.gpu?.destroy();
      chartsRef.current.embeddings?.destroy();
      chartsRef.current = {};
    };
  }, [isOpen, telemetryAvailable]);

  useEffect(() => {
    if (!isOpen || !telemetryAvailable || !websocketUrl) return undefined;

    let ws: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let reconnectAttempts = 0;
    const maxReconnectAttempts = 10;

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

    const processMetrics = (payload: unknown) => {
      const metricsArray = Array.isArray(payload) ? payload : (payload as { metrics?: unknown }).metrics;
      if (!Array.isArray(metricsArray)) return;

      const next: Partial<MetricState> = {};
      const engineUsage: Record<string, number> = {};
      let gpuPower: number | null = null;
      let pkgPower: number | null = null;

      metricsArray.forEach((metric: any) => {
        const { name, fields = {}, tags = {} } = metric || {};
        switch (name) {
          case 'cpu':
            if (typeof fields.usage_user === 'number') {
              next.cpu = fields.usage_user;
              pushSample(chartsRef.current.cpu, next.cpu);
            }
            break;
          case 'mem':
            if (typeof fields.used_percent === 'number') {
              next.ram = fields.used_percent;
              pushSample(chartsRef.current.ram, next.ram);
            }
            break;
          case 'gpu_engine_usage':
            if (typeof fields.usage === 'number' && typeof tags.engine === 'string') {
              engineUsage[tags.engine.toUpperCase()] = fields.usage;
            }
            break;
          case 'gpu_frequency':
            if (typeof fields.value === 'number' && tags.type === 'cur_freq') {
              next.gpuFreq = fields.value;
            }
            break;
          case 'gpu_power':
            if (typeof fields.value === 'number') {
              if (tags.type === 'gpu_cur_power') {
                gpuPower = fields.value;
              } else if (tags.type === 'pkg_cur_power') {
                pkgPower = fields.value;
              }
            }
            break;
          case 'dataprep_embeddings_per_second':
            if (typeof fields.value === 'number') {
              next.embeddingsPerSecond = fields.value;
              pushSample(chartsRef.current.embeddings, next.embeddingsPerSecond);
            }
            break;
          default:
            break;
        }
      });

      const engineNames = Object.keys(engineUsage);
      if (engineNames.length > 0) {
        const maxGpuUsage = Math.max(...Object.values(engineUsage));
        next.gpu = maxGpuUsage;
        next.gpuEngines = engineUsage;
        pushSample(chartsRef.current.gpu, maxGpuUsage);
      }

      if (gpuPower !== null) next.gpuPower = gpuPower;
      if (pkgPower !== null) next.pkgPower = pkgPower;

      setMetrics((prev) => ({ ...prev, ...next }));
      setLastUpdated(new Date());
    };

    const connect = () => {
      ws = new WebSocket(websocketUrl);

      ws.onopen = () => {
        reconnectAttempts = 0;
        setCollectorConnected(true);
        setTelemetryAvailable(true);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          processMetrics(data.metrics ?? data);
        } catch (err) {
          console.error('Telemetry metrics parse error', err);
        }
      };

      ws.onerror = () => {
        setCollectorConnected(false);
      };

      ws.onclose = () => {
        setCollectorConnected(false);
        setTelemetryAvailable(false);
        if (reconnectAttempts < maxReconnectAttempts) {
          reconnectAttempts += 1;
          reconnectTimer = setTimeout(connect, 3000);
        }
      };
    };

    connect();

    return () => {
      if (reconnectTimer) clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, [isOpen, telemetryAvailable, websocketUrl]);

  const engineLine = metrics.gpuEngines
    ? Object.entries(metrics.gpuEngines)
        .map(([engine, value]) => `${engine}: ${value.toFixed(1)}%`)
        .join(' | ')
    : null;

  if (!statusChecked || !telemetryAvailable) {
    return null;
  }

  return (
    <PanelWrapper>
      <Accordion align='start' size='sm'>{/* Default collapsed */}
        <AccordionItem
          title='System telemetry'
          open={isOpen}
          onHeadingClick={() => setIsOpen((prev) => !prev)}
        >
          <ScrollBody>
            <StatusRow>
              <StatusDot $active={collectorConnected} />
              <div>{collectorConnected ? 'Collector connected' : 'Collector disconnected'}</div>
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
                    : '—'}
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
                {metrics.gpuFreq !== undefined && metrics.gpuFreq !== null && (
                  <MetricSubtext>Freq: {metrics.gpuFreq.toFixed(0)} MHz</MetricSubtext>
                )}
                {metrics.gpuPower !== undefined && metrics.gpuPower !== null && (
                  <MetricSubtext>
                    Power: {metrics.gpuPower.toFixed(1)}W{metrics.pkgPower ? ` (Pkg: ${metrics.pkgPower.toFixed(1)}W)` : ''}
                  </MetricSubtext>
                )}
                {engineLine && <MetricSubtext>{engineLine}</MetricSubtext>}
                <div style={{ height: '180px' }}>
                  <canvas ref={gpuCanvasRef} aria-label='gpu-chart'></canvas>
                </div>
              </MetricChartCard>
            </MetricChartGrid>

            <DetailLine style={{ marginTop: '0.75rem' }}>
              Metrics sourced from vippet collector via telemetry gateway.
            </DetailLine>
          </ScrollBody>
        </AccordionItem>
      </Accordion>
    </PanelWrapper>
  );
};

export default TelemetryAccordion;
