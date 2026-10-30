// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { createAsyncThunk, createSelector, createSlice } from '@reduxjs/toolkit';
import axios from 'axios';
import { APP_URL } from '../../config';
import { buildTagIndex, GeoState, parseGeoResponse } from './geo';
import { RootState } from '../store';

export const GEO_REFRESH_INTERVAL_MS = 60_000;

export interface GeoSliceState extends GeoState {
  mapDrawerOpen: boolean;
}

export const initialState: GeoSliceState = {
  intersections: {},
  source: 'none',
  stale: false,
  loaded: false,
  mapDrawerOpen: false,
};

export const LoadIntersections = createAsyncThunk('geo/loadIntersections', async () => {
  const res = await axios.get(`${APP_URL}/geo/intersections`);
  return parseGeoResponse(res.data);
});

export const GeoSlice = createSlice({
  name: 'geo',
  initialState,
  reducers: {
    openMapDrawer: (state) => {
      state.mapDrawerOpen = true;
    },
    closeMapDrawer: (state) => {
      state.mapDrawerOpen = false;
    },
    toggleMapDrawer: (state) => {
      state.mapDrawerOpen = !state.mapDrawerOpen;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(LoadIntersections.fulfilled, (state, action) => {
        state.intersections = action.payload.intersections;
        state.source = action.payload.source;
        state.stale = action.payload.stale;
        state.loaded = true;
      })
      .addCase(LoadIntersections.rejected, (state) => {
        // Keep the last known intersections; the backend being briefly unreachable must not clear the map.
        state.stale = Object.keys(state.intersections).length > 0;
        state.loaded = true;
      });
  },
});

// Falls back to defaults so shared components still render in stores built without the geo slice.
const selectGeoState = (state: RootState): GeoSliceState => state.geo ?? initialState;

export const geoSelector = createSelector([selectGeoState], (geo) => ({
  intersections: geo.intersections,
  source: geo.source,
  stale: geo.stale,
  loaded: geo.loaded,
  hasIntersections: Object.keys(geo.intersections).length > 0,
  tagIndex: buildTagIndex(geo.intersections),
  mapDrawerOpen: geo.mapDrawerOpen,
}));

export const GeoReducer = GeoSlice.reducer;
export const GeoActions = GeoSlice.actions;
