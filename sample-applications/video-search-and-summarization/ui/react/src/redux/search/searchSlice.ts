// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { createAsyncThunk, createSelector, createSlice, PayloadAction } from '@reduxjs/toolkit';
import { SearchQuery, SearchState } from './search';
import { RootState } from '../store';
import axios from 'axios';
import { APP_URL } from '../../config';

const initialState: SearchState = {
  searchQueries: [],
  unreads: [],
  selectedQuery: null,
  triggerLoad: true,
};

export const SearchSlice = createSlice({
  name: 'search',
  initialState,
  reducers: {
    selectQuery: (state: SearchState, action: PayloadAction<string | null>) => {
      state.selectedQuery = action.payload;
    },
    removeSearchQuery: (state: SearchState, action) => {
      state.searchQueries = state.searchQueries.filter((query) => query.queryId !== action.payload.queryId);
    },
    updateSearchQuery: (state: SearchState, action) => {
      const index = state.searchQueries.findIndex((query) => query.queryId === action.payload.queryId);
      if (index !== -1) {
        state.searchQueries[index] = { ...state.searchQueries[index], ...action.payload };
      }
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(SearchLoad.pending, (state) => {
        state.searchQueries = [];
      })
      .addCase(SearchLoad.fulfilled, (state, action) => {
        state.triggerLoad = false;
        state.searchQueries = action.payload;
      })
      .addCase(SearchLoad.rejected, (state) => {
        state.triggerLoad = false;
        state.searchQueries = [];
      })
      .addCase(SearchAdd.fulfilled, (state, action) => {
        state.searchQueries.push(action.payload);
        state.selectedQuery = action.payload.queryId;
      })
      .addCase(SearchWatch.fulfilled, (state) => {
        state.triggerLoad = true;
      })
      .addCase(SearchRemove.fulfilled, (state) => {
        state.triggerLoad = true;
      });
  },
});

export const SearchRemove = createAsyncThunk('search/remove', async (queryId: string) => {
  const queryRes = await axios.delete<SearchQuery>(`${APP_URL}/search/${queryId}`);
  return queryRes.data;
});

export const SearchWatch = createAsyncThunk(
  'search/watch',
  async ({ queryId, watch }: { queryId: string; watch: boolean }) => {
    console.log('WATCH DATA', queryId, watch);

    const queryRes = await axios.patch<SearchQuery>(`${APP_URL}/search/${queryId}/watch`, { watch });
    return queryRes.data;
  },
);

export const SearchAdd = createAsyncThunk('search/add', async (query: string) => {
  const queryRes = await axios.post<SearchQuery>(`${APP_URL}/search`, {
    query,
  });
  return queryRes.data;
});

export const SearchLoad = createAsyncThunk('search/load', async () => {
  const queryRes = await axios.get<SearchQuery[]>(`${APP_URL}/search`);
  return queryRes.data;
});

const selectSearchState = (state: RootState) => state.search;

export const SearchSelector = createSelector([selectSearchState], (state) => ({
  queries: state.searchQueries,
  selectedQueryId: state.selectedQuery,
  unreads: state.unreads,
  triggerLoad: state.triggerLoad,
  selectedQuery: state.searchQueries.find((el) => el.queryId == state.selectedQuery),
  selectedResults: state.searchQueries.find((el) => el.queryId == state.selectedQuery)?.results || [],
}));

export const SearchActions = SearchSlice.actions;
export const SearchReducers = SearchSlice.reducer;
