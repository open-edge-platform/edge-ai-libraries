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

export const selectGpuMetric = (state: RootState) =>
  state.metrics.metrics.find(
    (m) =>
      m.name === "gpu_engine_usage" &&
      ["compute", "render", "ccs"].includes(m.tags?.engine ?? "") &&
      m.tags?.gpu_id === "0" &&
      (m.fields.usage as number) > 0,
  )?.fields?.usage as number | undefined;

export const selectGpu1Metric = (state: RootState) =>
  state.metrics.metrics.find(
    (m) =>
      m.name === "gpu_engine_usage" &&
      ["compute", "render", "ccs"].includes(m.tags?.engine ?? "") &&
      m.tags?.gpu_id === "1" &&
      (m.fields.usage as number) > 0,
  )?.fields?.usage as number | undefined;

export default metrics.reducer;
