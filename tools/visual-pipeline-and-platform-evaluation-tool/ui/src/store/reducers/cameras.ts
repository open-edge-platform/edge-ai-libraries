import { api as generatedApi } from "@/api/api.generated";
import type { RootState } from "@/store";
import type { Camera } from "@/api/api.generated";

/** Selectors for cameras from RTK Query cache */
export const selectCameras = (state: RootState): Camera[] =>
  generatedApi.endpoints.getCameras.select()(state)?.data ?? [];

export const selectCameraById = (state: RootState, cameraId: string) =>
  selectCameras(state).find((c) => c.device_id === cameraId);
