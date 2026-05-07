import { createSlice } from "@reduxjs/toolkit";
import type { PayloadAction } from "@reduxjs/toolkit";
import type { RootState } from "@/store";

export interface MetricData {
  name: string;
  labels: Record<string, string>;
  value: number;
  timestamp: number;
}

export interface MetricsMessage {
  timestamp: number;
  metrics: MetricData[];
}

export interface MetricsErrorMessage {
  error: string;
  timestamp: number;
}

export interface MetricsState {
  isConnected: boolean;
  isConnecting: boolean;
  lastMessage: string;
  metrics: MetricData[];
  error: string | null;
}

const initialState: MetricsState = {
  isConnected: false,
  isConnecting: false,
  lastMessage: "",
  metrics: [],
  error: null,
};

export const metrics = createSlice({
  name: "metrics",
  initialState,
  reducers: {
    streamConnecting: (state) => {
      state.isConnecting = true;
      state.isConnected = false;
      state.error = null;
    },
    streamConnected: (state) => {
      state.isConnected = true;
      state.isConnecting = false;
      state.error = null;
    },
    streamDisconnected: (state) => {
      state.isConnected = false;
      state.isConnecting = false;
      state.metrics = [];
    },
    streamReconnecting: (state, action: PayloadAction<string>) => {
      state.isConnected = false;
      state.isConnecting = true;
      state.error = action.payload;
      state.metrics = [];
    },
    streamError: (state, action: PayloadAction<string>) => {
      state.error = action.payload;
      state.isConnected = false;
      state.isConnecting = false;
      state.metrics = [];
    },
    messageReceived: (state, action: PayloadAction<string>) => {
      state.lastMessage = action.payload;
      try {
        const parsed = JSON.parse(action.payload) as
          | MetricsMessage
          | MetricsErrorMessage;
        if ("error" in parsed) {
          state.error = parsed.error;
          state.isConnected = false;
          state.isConnecting = true;
          state.metrics = [];
          return;
        }
        if (
          "metrics" in parsed &&
          parsed.metrics &&
          Array.isArray(parsed.metrics)
        ) {
          state.metrics = parsed.metrics;
          state.isConnected = true;
          state.isConnecting = false;
          state.error = null;
        }
      } catch (error) {
        console.error("Failed to parse metrics message:", error);
      }
    },
  },
});

export const {
  streamConnecting,
  streamConnected,
  streamDisconnected,
  streamReconnecting,
  streamError,
  messageReceived,
} = metrics.actions;

export const selectMetricsState = (state: RootState) => state.metrics;
export const selectIsConnected = (state: RootState) =>
  state.metrics.isConnected;
export const selectIsConnecting = (state: RootState) =>
  state.metrics.isConnecting;
export const selectMetrics = (state: RootState) => state.metrics.metrics;
export const selectLastMessage = (state: RootState) =>
  state.metrics.lastMessage;
export const selectError = (state: RootState) => state.metrics.error;

const findMetric = (
  metrics: MetricData[],
  name: string,
  labelMatcher?: (labels: Record<string, string>) => boolean,
) =>
  metrics.find(
    (m) => m.name === name && (labelMatcher ? labelMatcher(m.labels) : true),
  );

const filterMetrics = (
  metrics: MetricData[],
  name: string,
  labelMatcher?: (labels: Record<string, string>) => boolean,
) =>
  metrics.filter(
    (m) => m.name === name && (labelMatcher ? labelMatcher(m.labels) : true),
  );

export const selectFpsMetric = (state: RootState) =>
  findMetric(state.metrics.metrics, "fps")?.value;

export const selectCpuMetric = (state: RootState) =>
  findMetric(
    state.metrics.metrics,
    "cpu_usage_user",
    (l) => l.cpu === "cpu-total",
  )?.value;

export const selectMemoryMetric = (state: RootState) =>
  findMetric(state.metrics.metrics, "mem_used_percent")?.value;

export const selectCpuMetrics = (state: RootState) => {
  const userMetric = findMetric(
    state.metrics.metrics,
    "cpu_usage_user",
    (l) => l.cpu === "cpu-total",
  );
  const idleMetric = findMetric(
    state.metrics.metrics,
    "cpu_usage_idle",
    (l) => l.cpu === "cpu-total",
  );
  const cpuFrequencyMetric = findMetric(
    state.metrics.metrics,
    "cpu_frequency_avg_frequency",
  );
  const cpuTempMetric = findMetric(
    state.metrics.metrics,
    "temp_temp",
    (l) => l.sensor?.includes("coretemp_package_id") ?? false,
  );
  return {
    user: userMetric?.value ?? 0,
    idle: idleMetric?.value ?? 0,
    avgFrequency: (cpuFrequencyMetric?.value ?? 0) / 1_000_000,
    temp: cpuTempMetric?.value,
  };
};

export const selectGpuMetrics = (state: RootState, gpuId: string = "0") => {
  const gpuEngineMetrics = filterMetrics(
    state.metrics.metrics,
    "gpu_engine_usage_usage",
    (l) => l.gpu_id === gpuId,
  );

  const gpuFrequencyMetric = findMetric(
    state.metrics.metrics,
    "gpu_frequency",
    (l) => l.gpu_id === gpuId && l.type === "cur_freq",
  );

  const gpuPowerMetrics = filterMetrics(
    state.metrics.metrics,
    "gpu_power",
    (l) => l.gpu_id === gpuId,
  );

  // Map short engine names to long names emitted by qmassa.
  const engineNameMap: Record<string, string> = {
    rcs: "render",
    bcs: "copy",
    vcs: "video",
    vecs: "video-enhance",
    ccs: "compute",
  };

  const findEngineUsage = (engineNames: string[]) => {
    const metric = gpuEngineMetrics.find((m) => {
      const engine = m.labels.engine ?? "";
      return (
        engineNames.includes(engine) ||
        engineNames.includes(engineNameMap[engine] ?? engine)
      );
    });
    return metric?.value;
  };

  const findPowerValue = (powerType: string) => {
    const metric = gpuPowerMetrics.find((m) => m.labels.type === powerType);
    return metric?.value;
  };

  return {
    compute: findEngineUsage(["compute", "ccs"]),
    render: findEngineUsage(["render", "rcs"]),
    copy: findEngineUsage(["copy", "bcs"]),
    video: findEngineUsage(["video", "vcs"]),
    videoEnhance: findEngineUsage(["video-enhance", "vecs"]),
    frequency:
      gpuFrequencyMetric?.value !== undefined
        ? gpuFrequencyMetric.value / 1000
        : undefined,
    gpuPower: findPowerValue("gpu_cur_power"),
    pkgPower: findPowerValue("pkg_cur_power"),
  };
};

export default metrics.reducer;
