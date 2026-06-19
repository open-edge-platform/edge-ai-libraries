import { configureStore } from "@reduxjs/toolkit";
import { persistStore, persistReducer } from "redux-persist";
import { api } from "@/api/api.generated.ts";
import metricsReducer from "./reducers/metrics.ts";
import pipelinesReducer from "./reducers/pipelines.ts";
import modelsReducer from "./reducers/models.ts";
import devicesReducer from "./reducers/devices.ts";
import uiConfigReducer from "./reducers/uiConfig.ts";

// wrapper for redux-persist
const storage = {
  getItem: (key: string) => Promise.resolve(window.localStorage.getItem(key)),
  setItem: (key: string, value: string) => {
    window.localStorage.setItem(key, value);
    return Promise.resolve(value);
  },
  removeItem: (key: string) => {
    window.localStorage.removeItem(key);
    return Promise.resolve();
  },
};

const persistUiConfig = {
  key: "uiConfig",
  storage,
};

const persistedUiConfigReducer = persistReducer(
  persistUiConfig,
  uiConfigReducer,
);

export const store = configureStore({
  reducer: {
    [api.reducerPath]: api.reducer,
    metrics: metricsReducer,
    pipelines: pipelinesReducer,
    models: modelsReducer,
    devices: devicesReducer,
    uiConfig: persistedUiConfigReducer,
  },
  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware({
      serializableCheck: {
        ignoredActions: ["persist/PERSIST", "persist/REHYDRATE"],
      },
    }).concat(api.middleware),
});

export const persistor = persistStore(store);

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
