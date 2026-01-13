import { createSlice, createSelector } from "@reduxjs/toolkit";
import type { Device } from "@/api/api.generated";
import type { RootState } from "@/store";

interface DevicesState {
  items: Device[];
  lastFetched: number | null;
}

const initialState: DevicesState = {
  items: [],
  lastFetched: null,
};

const devicesSlice = createSlice({
  name: "devices",
  initialState,
  reducers: {
    setDevices: (state, action: { payload: Device[] }) => {
      state.items = action.payload;
      state.lastFetched = Date.now();
    },
    setTestDevices: (state, action: { payload: Device[] }) => {
      state.items = action.payload;
      state.lastFetched = Date.now();
    },
  },
});

export const { setDevices, setTestDevices } = devicesSlice.actions;

// Base selector
export const selectDevices = (state: RootState) => state.devices.items;

export const selectDevicesMap = createSelector([selectDevices], (devices) => {
  const map = new Map<string, Device>();
  devices.forEach((d) => map.set(d.device_name, d));
  return map;
});

// Optimized selectors using the map
export const selectDeviceByName = (state: RootState, deviceName: string) =>
  selectDevicesMap(state).get(deviceName);

export const selectDeviceByFamily = (state: RootState, deviceFamily: string) =>
  selectDevices(state).find((device) => device.device_family === deviceFamily);

export const selectHasNPU = createSelector([selectDevices], (devices) =>
  devices.some((device) => device.device_family === "NPU"),
);

export const selectGpuDevices = createSelector([selectDevices], (devices) =>
  devices
    .filter((device) => device.device_family === "GPU")
    .sort((d1, d2) => d1.device_name.localeCompare(d2.device_name)),
);

export default devicesSlice.reducer;
