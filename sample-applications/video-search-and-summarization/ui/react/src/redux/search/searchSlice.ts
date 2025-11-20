// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { createAsyncThunk, createSelector, createSlice, PayloadAction } from '@reduxjs/toolkit';
import { SearchQuery, SearchQueryDTO, SearchQueryStatus, SearchQueryUI, SearchResult, SearchState } from './search';
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
      if (index !== -1) {
        // Preserve existing topK when updating
        const currentTopK = state.searchQueries[index].topK;
        state.searchQueries[index] = { ...state.searchQueries[index], ...action.payload, topK: currentTopK };
      } else {
        state.searchQueries.push({ ...action.payload, topK: defaultTopk });
      }
      state.unreads.push(action.payload.queryId);
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
  },
  extraReducers: (builder) => {
    builder
      .addCase(SearchLoad.fulfilled, (state, action) => {
        state.triggerLoad = false;
        if (action.payload.length === 0) {
          state.searchQueries = [];
        } else {
          state.searchQueries = action.payload.map((query) => ({ ...query, topK: defaultTopk }));
        }
      })
      .addCase(SearchSync.fulfilled, (state, action) => {
        if (action.payload && action.payload.queryId) {
          const index = state.searchQueries.findIndex((query) => query.queryId === action.payload!.queryId);
          if (index !== -1) {
            state.searchQueries[index] = { ...state.searchQueries[index], ...action.payload };
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
          state.searchQueries[index] = { ...state.searchQueries[index], ...action.payload };
        }
      })
      .addCase(SearchAdd.fulfilled, (state, action) => {
        state.searchQueries.push({ ...action.payload, topK: defaultTopk });
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

export const RerunSearch = createAsyncThunk('search/rerun', async (queryId: string) => {
  const queryRes = await axios.post<SearchQuery>(`${APP_URL}/search/${queryId}/refetch`);
  return queryRes.data;
});

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

export const SearchAdd = createAsyncThunk('search/add', async ({ query, tags }: { query: string; tags: string[] }) => {
  const searchQuery: SearchQueryDTO = { query };

  if (tags && tags.length > 0) {
    searchQuery.tags = tags.join(',');
  }

  const queryRes = await axios.post<SearchQuery>(`${APP_URL}/search`, searchQuery);
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
