import { api as generatedApi } from "@/api/api.generated";
import type { RootState } from "@/store";
import type { Video } from "@/api/api.generated";

/** Selectors for videos from RTK Query cache */
export const selectVideos = (state: RootState): Video[] =>
  generatedApi.endpoints.getVideos.select()(state)?.data ?? [];

export const selectVideoByFilename = (state: RootState, filename: string) =>
  selectVideos(state).find((v) => v.filename === filename);
