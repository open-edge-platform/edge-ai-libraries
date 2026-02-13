// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { createAsyncThunk, createSelector, createSlice, PayloadAction } from '@reduxjs/toolkit';
import {
  SearchQuery,
  SearchQueryDTO,
  SearchQueryStatus,
  SearchQueryUI,
  SearchResult,
  SearchState,
  TimeFilterSelection,
} from './search';
import { RootState } from '../store';
import axios from 'axios';
import { APP_URL } from '../../config';

const initialState: SearchState = {
  searchQueries: [],
  unreads: [],
  selectedQuery: null,
  triggerLoad: true,
  suggestedTags: [],
};

const defaultTopk = 4;

// Ensure each query has its own normalized time filter; default to 0 minutes when absent.
const normalizeTimeFilter = (timeFilter?: TimeFilterSelection | null): TimeFilterSelection | null => {
  if (timeFilter === null) return { value: 0, unit: 'minutes' };
  if (!timeFilter || typeof timeFilter !== 'object') return { value: 0, unit: 'minutes' };
  return {
    ...timeFilter,
    value: timeFilter.value ?? 0,
    unit: timeFilter.unit ?? 'minutes',
  };
};

export const SearchSlice = createSlice({
  name: 'search',
  initialState,
  reducers: {
    selectQuery: (state: SearchState, action: PayloadAction<string | null>) => {
      if (action.payload) {
        if (action.payload !== state.selectedQuery) {
          const index = state.searchQueries.findIndex((query) => query.queryId === action.payload);
          if (index !== -1) {
            state.selectedQuery = action.payload;
          }
        }

        state.unreads = state.unreads.filter((id) => id !== action.payload);
      }
    },
    removeSearchQuery: (state: SearchState, action) => {
      state.searchQueries = state.searchQueries.filter((query) => query.queryId !== action.payload.queryId);
    },
    updateSearchQuery: (state: SearchState, action) => {
      console.log('searchState action.payload', action.payload);
      const index = state.searchQueries.findIndex((query) => query.queryId === action.payload.queryId);
      const currentTopK = index !== -1 ? state.searchQueries[index].topK : defaultTopk;
      const merged = index !== -1
        ? { ...state.searchQueries[index], ...action.payload, topK: currentTopK }
        : { ...action.payload, topK: currentTopK };

      // Normalize per-query time filter to avoid leaking values across queries.
      merged.timeFilter = normalizeTimeFilter(merged.timeFilter);

      const hasResults = Array.isArray(merged.results) && merged.results.length > 0;
      const normalized = {
        ...merged,
        queryStatus:
          hasResults && merged.queryStatus === SearchQueryStatus.RUNNING
            ? SearchQueryStatus.IDLE
            : merged.queryStatus,
      };

      console.log('[searchSlice] upsert query', {
        queryId: action.payload.queryId,
        prevLength: index !== -1 ? state.searchQueries[index].results?.length : undefined,
        nextLength: normalized.results?.length,
        selectedQuery: state.selectedQuery,
      });

      // Deduplicate: keep only one entry per queryId (latest wins) to avoid stale copies blocking render.
      state.searchQueries = [
        ...state.searchQueries.filter((query) => query.queryId !== action.payload.queryId),
        normalized,
      ];

      state.unreads.push(action.payload.queryId);
      // If nothing is selected, auto-select the updated query so UI can render results from sockets
      if (!state.selectedQuery || state.selectedQuery === action.payload.queryId) {
        state.selectedQuery = action.payload.queryId;
      }
      console.log('[searchSlice] state after update', {
        selectedQuery: state.selectedQuery,
        totalQueries: state.searchQueries.length,
        selectedResults: state.searchQueries.find((q) => q.queryId === state.selectedQuery)?.results?.length,
      });
    },
    syncSearch: (state: SearchState, action) => {
      const index = state.searchQueries.findIndex((query) => query.queryId === action.payload.queryId);
      if (index !== -1) {
        state.searchQueries[index] = { ...state.searchQueries[index], ...action.payload };
        state.unreads.push(action.payload.queryId);
      }
    },
    markRead: (state: SearchState, action) => {
      const queryId = action.payload.queryId;
      state.unreads = state.unreads.filter((id) => id !== queryId);
    },
    updateTopK: (state: SearchState, action: PayloadAction<{ queryId: string; topK: number }>) => {
      state.searchQueries[state.searchQueries.findIndex((query) => query.queryId === action.payload.queryId)].topK =
        action.payload.topK;
    },
    updateTimeFilter: (
      state: SearchState,
      action: PayloadAction<{ queryId: string; timeFilter: TimeFilterSelection | null }>,
    ) => {
      const index = state.searchQueries.findIndex((query) => query.queryId === action.payload.queryId);
      if (index !== -1) {
        state.searchQueries[index].timeFilter = normalizeTimeFilter(action.payload.timeFilter);
        state.searchQueries[index].queryStatus = SearchQueryStatus.RUNNING; // mark in-progress so UI greys out
      }
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(SearchLoad.fulfilled, (state, action) => {
        state.triggerLoad = false;
        if (action.payload.length === 0) {
          state.searchQueries = [];
        } else {
          state.searchQueries = action.payload.map((query) => ({
            ...query,
            topK: defaultTopk,
            timeFilter: normalizeTimeFilter(query.timeFilter),
          }));
        }
      })
      .addCase(SearchSync.fulfilled, (state, action) => {
        if (action.payload && action.payload.queryId) {
          const index = state.searchQueries.findIndex((query) => query.queryId === action.payload!.queryId);
          if (index !== -1) {
            state.searchQueries[index] = {
              ...state.searchQueries[index],
              ...action.payload,
              timeFilter: normalizeTimeFilter(action.payload.timeFilter),
            };
          }
        }
      })
      .addCase(LoadTags.fulfilled, (state, action) => {
        state.suggestedTags = action.payload;
      })
      .addCase(SearchLoad.rejected, (state) => {
        state.triggerLoad = false;
        state.searchQueries = [];
      })
      .addCase(RerunSearch.fulfilled, (state, action) => {
        const index = state.searchQueries.findIndex((query) => query.queryId === action.payload.queryId);
        if (index !== -1) {
          state.searchQueries[index] = {
            ...state.searchQueries[index],
            ...action.payload,
            timeFilter: normalizeTimeFilter(action.payload.timeFilter),
          };
        }
      })
      .addCase(RerunSearch.rejected, (state, action) => {
        const { queryId } = action.meta.arg;
        const index = state.searchQueries.findIndex((query) => query.queryId === queryId);
        if (index !== -1) {
          state.searchQueries[index].queryStatus = SearchQueryStatus.ERROR;
        }
      })
      .addCase(RerunSearch.pending, (state, action) => {
        const { queryId } = action.meta.arg;
        const index = state.searchQueries.findIndex((query) => query.queryId === queryId);
        if (index !== -1) {
          state.searchQueries[index].queryStatus = SearchQueryStatus.RUNNING;
        }
      })
      .addCase(SearchAdd.fulfilled, (state, action) => {
        const existingIndex = state.searchQueries.findIndex((query) => query.queryId === action.payload.queryId);
        const existingTopK = existingIndex !== -1 ? state.searchQueries[existingIndex].topK : defaultTopk;

        const merged = {
          ...(existingIndex !== -1 ? state.searchQueries[existingIndex] : {}),
          ...action.payload,
          topK: existingTopK,
          timeFilter: normalizeTimeFilter(action.payload.timeFilter),
        };

        state.searchQueries = [
          ...state.searchQueries.filter((query) => query.queryId !== action.payload.queryId),
          merged,
        ];

        state.selectedQuery = action.payload.queryId;
      })
      .addCase(SearchWatch.pending, (state, action) => {
        const { queryId, watch } = action.meta.arg;
        const index = state.searchQueries.findIndex((query) => query.queryId === queryId);
        if (index !== -1) {
          state.searchQueries[index].watch = watch;
        }
      })
      .addCase(SearchRemove.fulfilled, (state) => {
        state.triggerLoad = true;
      });
  },
});

export const LoadTags = createAsyncThunk('search/loadTags', async () => {
  const res = await axios.get<string[]>(`${APP_URL}/tags`);
  return res.data;
});

export const RerunSearch = createAsyncThunk(
  'search/rerun',
  async ({ queryId, timeFilter }: { queryId: string; timeFilter?: TimeFilterSelection | null }) => {
    console.log('[RerunSearch] start', { queryId, timeFilter });
    const body = timeFilter !== undefined ? { timeFilter } : undefined;
    const queryRes = await axios.post<SearchQuery>(`${APP_URL}/search/${queryId}/refetch`, body);
    console.log('[RerunSearch] success', { queryId, timeFilter, results: queryRes.data?.results?.length });
    return queryRes.data;
  },
);

export const SearchRemove = createAsyncThunk('search/remove', async (queryId: string) => {
  const queryRes = await axios.delete<SearchQuery>(`${APP_URL}/search/${queryId}`);
  return queryRes.data;
});

export const SearchSync = createAsyncThunk('search/sync', async (queryId: string) => {
  const res = await axios.post<SearchQuery | null>(`${APP_URL}/search/${queryId}/refetch`);
  return res.data;
});

export const SearchWatch = createAsyncThunk(
  'search/watch',
  async ({ queryId, watch }: { queryId: string; watch: boolean }) => {
    console.log('WATCH DATA', queryId, watch);

    const queryRes = await axios.patch<SearchQuery>(`${APP_URL}/search/${queryId}/watch`, { watch });
    return queryRes.data;
  },
);

export const SearchAdd = createAsyncThunk(
  'search/add',
  async ({ query, tags, timeFilter }: { query: string; tags: string[]; timeFilter?: TimeFilterSelection | null }) => {
    const searchQuery: SearchQueryDTO = { query };

    if (tags && tags.length > 0) {
      searchQuery.tags = tags.join(',');
    }

    if (timeFilter !== undefined) {
      searchQuery.timeFilter = timeFilter;
    }

    const queryRes = await axios.post<SearchQuery>(`${APP_URL}/search`, searchQuery);
    return queryRes.data;
  },
);

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
  suggestedTags: state.suggestedTags,
  queriesInProgress: state.searchQueries.filter((query) => query.queryStatus === SearchQueryStatus.RUNNING),
  queriesWithErrors: state.searchQueries.filter((query) => query.queryStatus === SearchQueryStatus.ERROR),
  isSelectedInProgress:
    state.selectedQuery &&
    state.searchQueries
      .filter((query) => query.queryStatus === SearchQueryStatus.RUNNING)
      .map((curr) => curr.queryId)
      .includes(state.selectedQuery),
  isSelectedHasError:
    state.selectedQuery &&
    state.searchQueries
      .filter((query) => query.queryStatus === SearchQueryStatus.ERROR)
      .map((curr) => curr.queryId)
      .includes(state.selectedQuery),
  selectedResults: state.searchQueries.reduce((acc: SearchResult[], curr: SearchQueryUI) => {
    if (curr.queryId === state.selectedQuery) {
      if (!curr || !curr.results || (curr.results && curr.results.length <= 0)) {
        return [];
      }
      acc = curr.results.slice(0, curr.topK);
    }
    return acc;
  }, [] as SearchResult[]),
}));

export const SearchActions = SearchSlice.actions;
export const SearchReducers = SearchSlice.reducer;
