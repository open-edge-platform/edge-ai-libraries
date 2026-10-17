// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
//
// Sample slice for cross-cutting UI state (active screen, connection status,
// right-panel collapsed, etc.). Replace with the target app's real state.

import { createSlice } from '@reduxjs/toolkit';
import type { PayloadAction } from '@reduxjs/toolkit';

export type ConnectionStatus = 'connected' | 'connecting' | 'disconnected';

interface UiState {
  activeScreen: string;
  connectionStatus: ConnectionStatus;
  isRightPanelCollapsed: boolean;
}

const initialState: UiState = {
  activeScreen: 'main',
  connectionStatus: 'disconnected',
  isRightPanelCollapsed: false,
};

const uiSlice = createSlice({
  name: 'ui',
  initialState,
  reducers: {
    setActiveScreen(state, action: PayloadAction<string>) {
      state.activeScreen = action.payload;
    },
    setConnectionStatus(state, action: PayloadAction<ConnectionStatus>) {
      state.connectionStatus = action.payload;
    },
    toggleRightPanel(state) {
      state.isRightPanelCollapsed = !state.isRightPanelCollapsed;
    },
  },
});

export const { setActiveScreen, setConnectionStatus, toggleRightPanel } = uiSlice.actions;
export default uiSlice.reducer;
