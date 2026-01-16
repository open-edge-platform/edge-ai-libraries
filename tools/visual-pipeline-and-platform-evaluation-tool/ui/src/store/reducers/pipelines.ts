import { createSlice, createSelector } from "@reduxjs/toolkit";
import type { Pipeline } from "@/api/api.generated";
import type { RootState } from "@/store";

interface PipelinesState {
  items: Pipeline[];
  lastFetched: number | null;
}

const initialState: PipelinesState = {
  items: [],
  lastFetched: null,
};

const pipelinesSlice = createSlice({
  name: "pipelines",
  initialState,
  reducers: {
    setPipelines: (state, action: { payload: Pipeline[] }) => {
      state.items = action.payload;
      state.lastFetched = Date.now();
    },
  },
});

export const { setPipelines } = pipelinesSlice.actions;

// Base selector
export const selectPipelines = (state: RootState) => state.pipelines.items;

export const selectPipelinesMap = createSelector(
  [selectPipelines],
  (pipelines) => {
    const map = new Map<string, Pipeline>();
    pipelines.forEach((p) => map.set(p.id, p));
    return map;
  },
);

// Optimized selectors using the map
export const selectPipelineById = (state: RootState, pipelineId: string) =>
  selectPipelinesMap(state).get(pipelineId);

export const selectPipelineNameById = (state: RootState, pipelineId: string) =>
  selectPipelinesMap(state).get(pipelineId)?.name ?? pipelineId;

export default pipelinesSlice.reducer;
