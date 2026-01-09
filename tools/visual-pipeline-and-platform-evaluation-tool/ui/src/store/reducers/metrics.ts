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
  testMode: boolean;
}

const initialState: MetricsState = {
  isConnected: false,
  isConnecting: false,
  lastMessage: "",
  metrics: [],
  error: null,
  testMode: false,
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
      if (state.testMode) return; // Don't update metrics if in test mode
      
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
    setTestMetrics: (state, action: PayloadAction<MetricData[]>) => {
      state.metrics = action.payload;
      state.isConnected = true;
      state.testMode = true;
    },
    clearTestMode: (state) => {
      state.testMode = false;
      state.metrics = [];
      state.isConnected = false;
    },
  },
});

export const {
  wsConnecting,
  wsConnected,
  wsDisconnected,
  wsError,
  messageReceived,
  setTestMetrics,
  clearTestMode,
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

// Dynamic GPU metrics selector - returns array of GPU metrics with their IDs
export const selectAllGpuMetrics = (state: RootState) => {
  const gpuMetrics = state.metrics.metrics.filter(
    (m) =>
      m.name === "gpu_engine_usage" &&
      ["compute", "render", "ccs"].includes(m.tags?.engine ?? "") &&
      (m.fields.usage as number) > 0,
  );

  // Group by gpu_id and return the first metric for each GPU
  const gpuMap = new Map<string, { id: string; usage: number }>();
  gpuMetrics.forEach((metric) => {
    const gpuId = metric.tags?.gpu_id;
    if (gpuId && !gpuMap.has(gpuId)) {
      gpuMap.set(gpuId, {
        id: gpuId,
        usage: metric.fields.usage as number,
      });
    }
  });

  return Array.from(gpuMap.values()).sort((a, b) =>
    a.id.localeCompare(b.id),
  );
}

export default metrics.reducer;
