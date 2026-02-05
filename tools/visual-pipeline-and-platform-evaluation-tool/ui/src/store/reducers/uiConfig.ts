import { createSlice, type PayloadAction } from "@reduxjs/toolkit";
import type { RootState } from "@/store";

interface UiConfigState {
  sidebarOpen: boolean;
}

const initialState: UiConfigState = {
  sidebarOpen: true,
};

const uiConfigSlice = createSlice({
  name: "uiConfig",
  initialState,
  reducers: {
    setSidebarOpen: (state, action: PayloadAction<boolean>) => {
      state.sidebarOpen = action.payload;
    },
    toggleSidebar: (state) => {
      state.sidebarOpen = !state.sidebarOpen;
    },
  },
});

export const { setSidebarOpen, toggleSidebar } = uiConfigSlice.actions;

export const selectSidebarOpen = (state: RootState) =>
  state.uiConfig.sidebarOpen;

export default uiConfigSlice.reducer;
