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
  },
});

export const { setDevices } = devicesSlice.actions;

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

export default devicesSlice.reducer;
