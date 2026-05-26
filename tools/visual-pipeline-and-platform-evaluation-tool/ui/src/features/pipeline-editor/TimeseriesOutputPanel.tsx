// SPDX-License-Identifier: Apache-2.0

import { useEffect, useMemo, useState } from "react";
import { MetricChart, type MetricDataPoint } from "@/features/metrics/MetricChart";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { highlightJson } from "@/lib/jsonUtils";
import "@/lib/hljs-theme.css";

const MAX_DATA_POINTS = 6;
const POLL_INTERVAL_MS = 5000;

interface IngestionRecord {
  timestamp: number;
  type: "ingestion";
  data: { grid_active_power: number; wind_speed: number };
  status: number;
}

interface AnalyticsRecord {
  inference_time_ms: number;
  end_to_end_time_ms: number;
  processing_point_time: number;
}

interface TimeseriesData {
  ingestion: IngestionRecord[];
  analytics: AnalyticsRecord[];
}

const TimeseriesOutputPanel = () => {
  const [data, setData] = useState<TimeseriesData>({ ingestion: [], analytics: [] });
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState("charts");

  // Poll the /api/v1/timeseries/data endpoint
  useEffect(() => {
    let active = true;

    const fetchData = async () => {
      try {
        const res = await fetch("/api/v1/timeseries/data?limit=60");
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = (await res.json()) as TimeseriesData;
        if (active) {
          setData(json);
          setError(null);
        }
      } catch (e) {
        if (active) setError(String(e));
      }
    };

    fetchData();
    const interval = setInterval(fetchData, POLL_INTERVAL_MS);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, []);

  // Chart data transforms
  const inferenceChart: MetricDataPoint[] = useMemo(
    () => data.analytics.map((r, i) => ({ timestamp: Date.now() - (data.analytics.length - i) * 5000, value: r.inference_time_ms })),
    [data.analytics],
  );

  const e2eChart: MetricDataPoint[] = useMemo(
    () => data.analytics.map((r, i) => ({ timestamp: Date.now() - (data.analytics.length - i) * 5000, value: r.end_to_end_time_ms })),
    [data.analytics],
  );

  const yMax = (pts: MetricDataPoint[]) => Math.ceil(Math.max(...pts.map((p) => p.value ?? 0), 1) * 1.2);

  // Latest records for metadata JSON display
  const latestIngestion = data.ingestion[data.ingestion.length - 1];
  const ingestionHtml = useMemo(
    () => (latestIngestion ? highlightJson(JSON.stringify(latestIngestion, null, 2)) : ""),
    [latestIngestion],
  );

  return (
    <div className="flex flex-col w-full h-full bg-background p-4 space-y-4 overflow-y-auto overflow-x-hidden min-w-0">
      <h2 className="text-lg font-semibold">Wind Turbine Anomaly Detection</h2>

      <div className="flex items-center gap-4 text-xs text-muted-foreground">
        <span>Ingestion: {data.ingestion.length} pts</span>
        <span>Analytics: {data.analytics.length} pts</span>
        {error && <span className="text-destructive">{error}</span>}
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="flex flex-col min-w-0">
        <TabsList>
          <TabsTrigger value="charts">Charts</TabsTrigger>
          <TabsTrigger value="metadata">Metadata JSON</TabsTrigger>
        </TabsList>

        <TabsContent value="charts" className="space-y-4 mt-2">
          {data.analytics.length > 0 && (
            <>
              <MetricChart
                title="Inference Time"
                data={inferenceChart}
                dataKeys={["value"]}
                colors={["var(--color-magenta-chart, #e879f9)"]}
                unit=" ms"
                yAxisDomain={[0, yMax(inferenceChart)]}
                showLegend={false}
                labels={["Inference Time"]}
                maxDataPoints={MAX_DATA_POINTS}
              />
              <MetricChart
                title="End-to-End Time"
                data={e2eChart}
                dataKeys={["value"]}
                colors={["var(--color-cyan-chart, #22d3ee)"]}
                unit=" ms"
                yAxisDomain={[0, yMax(e2eChart)]}
                showLegend={false}
                labels={["End-to-End Time"]}
                maxDataPoints={MAX_DATA_POINTS}
              />
            </>
          )}

          {data.ingestion.length === 0 && data.analytics.length === 0 && (
            <p className="text-sm text-muted-foreground">Waiting for data...</p>
          )}
        </TabsContent>

        <TabsContent value="metadata" className="space-y-4 mt-2">
          <div className="space-y-2">
            <h3 className="text-sm font-medium text-muted-foreground">Ingestion (latest)</h3>
            {ingestionHtml ? (
              <pre className="max-h-[30vh] overflow-auto border p-3 font-mono text-xs leading-5 whitespace-pre-wrap break-all bg-zinc-100 dark:bg-zinc-900/80">
                <code className="hljs" dangerouslySetInnerHTML={{ __html: ingestionHtml }} />
              </pre>
            ) : (
              <p className="text-sm text-muted-foreground">No data yet.</p>
            )}
          </div>

        </TabsContent>
      </Tabs>
    </div>
  );
};

export default TimeseriesOutputPanel;
