import { createSlice, createSelector } from "@reduxjs/toolkit";
import type { Model } from "@/api/api.generated";
import type { RootState } from "@/store";

interface ModelsState {
  items: Model[];
  lastFetched: number | null;
}

const initialState: ModelsState = {
  items: [],
  lastFetched: null,
};

const modelsSlice = createSlice({
  name: "models",
  initialState,
  reducers: {
    setModels: (state, action: { payload: Model[] }) => {
      state.items = action.payload;
      state.lastFetched = Date.now();
    },
  },
});

export const { setModels } = modelsSlice.actions;

// Base selector
export const selectModels = (state: RootState) => state.models.items;

export const selectModelsMap = createSelector([selectModels], (models) => {
  const map = new Map<string, Model>();
  models.forEach((m) => map.set(m.name, m));
  return map;
});

// Optimized selectors using the map
export const selectModelById = (state: RootState, modelId: string) =>
  selectModelsMap(state).get(modelId);

export const selectModelNameById = (state: RootState, modelId: string) =>
  selectModelsMap(state).get(modelId)?.name ?? modelId;

export default modelsSlice.reducer;
