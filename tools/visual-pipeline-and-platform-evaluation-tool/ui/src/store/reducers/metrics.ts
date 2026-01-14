import { createSlice } from "@reduxjs/toolkit";
import type { PayloadAction } from "@reduxjs/toolkit";
import type { RootState } from "@/store";
export interface MetricData {
  name: string;
  fields: Record<string, number | string>;
  tags?: Record<string, string>;
  timestamp?: string;
}
export interface MetricsMessage {
  metrics: MetricData[];
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
    wsConnecting: (state) => {
      state.isConnecting = true;
      state.isConnected = false;
      state.error = null;
    },
    wsConnected: (state) => {
      state.isConnected = true;
      state.isConnecting = false;
      state.error = null;
    },
    wsDisconnected: (state) => {
      state.isConnected = false;
      state.isConnecting = false;
    },
    wsError: (state, action: PayloadAction<string>) => {
      state.error = action.payload;
      state.isConnected = false;
      state.isConnecting = false;
    },
    messageReceived: (state, action: PayloadAction<string>) => {
      state.lastMessage = action.payload;
      try {
        const parsed = JSON.parse(action.payload) as MetricsMessage;
        if (parsed.metrics && Array.isArray(parsed.metrics)) {
          state.metrics = parsed.metrics;
        }
      } catch (error) {
        console.error("Failed to parse metrics message:", error);
      }
    },
  },
});
export const {
  wsConnecting,
  wsConnected,
  wsDisconnected,
  wsError,
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
export const selectFpsMetric = (state: RootState) =>
  state.metrics.metrics.find((m) => m.name === "fps")?.fields?.value as
    | number
    | undefined;
export const selectCpuMetric = (state: RootState) =>
  state.metrics.metrics.find((m) => m.name === "cpu")?.fields?.usage_user as
    | number
    | undefined;

export const selectMemoryMetric = (state: RootState) =>
  state.metrics.metrics.find((m) => m.name === "mem")?.fields?.used_percent as
    | number
    | undefined;

export const selectCpuMetrics = (state: RootState) => {
  const cpuMetric = state.metrics.metrics.find((m) => m.name === "cpu");
  const cpuFrequencyMetric = state.metrics.metrics.find(
    (m) => m.name === "cpu_frequency_avg",
  );
  const cpuTempMetric = state.metrics.metrics.find(
    (m) => m.name === "temp" && m.tags?.sensor?.includes("coretemp_package_id"),
  );
  return {
    user: (cpuMetric?.fields?.usage_user as number) ?? 0,
    idle: (cpuMetric?.fields?.usage_idle as number) ?? 0,
    avgFrequency:
      ((cpuFrequencyMetric?.fields?.frequency as number) ?? 0) / 1000000, // Convert kHz to GHz
    temp: cpuTempMetric?.fields?.temp as number | undefined,
  };
};

export const selectGpuMetrics = (state: RootState, gpuId: string = "0") => {
  const gpuMetrics = state.metrics.metrics.filter(
    (m) => m.name === "gpu_engine_usage" && m.tags?.gpu_id === gpuId,
  );

  const gpuFrequencyMetric = state.metrics.metrics.find(
    (m) => m.name === "gpu_frequency" && m.tags?.gpu_id === gpuId,
  );

  const gpuPowerMetrics = state.metrics.metrics.filter(
    (m) => m.name === "gpu_power" && m.tags?.gpu_id === gpuId,
  );

  // map short engine names to long names
  const engineNameMap: Record<string, string> = {
    rcs: "render",
    bcs: "copy",
    vcs: "video",
    vecs: "video-enhance",
    ccs: "compute",
  };

  const findEngineUsage = (engineNames: string[]) => {
    const metric = gpuMetrics.find((m) => {
      const engine = m.tags?.engine ?? "";
      return (
        engineNames.includes(engine) ||
        engineNames.includes(engineNameMap[engine] ?? engine)
      );
    });
    return metric ? (metric.fields?.usage as number | undefined) : undefined;
  };

  const findPowerValue = (powerType: string) => {
    const metric = gpuPowerMetrics.find((m) => m.tags?.type === powerType);
    return metric ? (metric.fields?.value as number | undefined) : undefined;
  };

  return {
    compute: findEngineUsage(["compute", "ccs"]),
    render: findEngineUsage(["render", "rcs"]),
    copy: findEngineUsage(["copy", "bcs"]),
    video: findEngineUsage(["video", "vcs"]),
    videoEnhance: findEngineUsage(["video-enhance", "vecs"]),
    frequency: gpuFrequencyMetric?.fields?.value
      ? (gpuFrequencyMetric.fields.value as number) / 1000
      : undefined,
    gpuPower: findPowerValue("gpu_cur_power"),
    pkgPower: findPowerValue("pkg_cur_power"),
  };
};

export default metrics.reducer;
