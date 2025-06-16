import { createSelector, createSlice, PayloadAction } from '@reduxjs/toolkit';
import {
  ChunkSummaryStatusFromFrames,
  CountStatus,
  StateActionStatus,
  UIFrameForState,
  UIFrameSummary,
  VideoFrameState,
} from './summary';
import { RootState } from '../store';

const initialState: VideoFrameState = {
  frames: {},
  frameSummaries: {},
  selectedSummary: null,
};

export const VideoFrameSlice = createSlice({
  name: 'VideoFrames',
  initialState,
  reducers: {
    addFrames: (state: VideoFrameState, action: PayloadAction<UIFrameForState[]>) => {
      const frames = action.payload.reduce((acc: Record<string, UIFrameForState>, curr) => {
        const { stateId, chunkId, frameId } = curr;
        const frameKey = [stateId, chunkId, frameId].join('#');
        acc[frameKey] = curr;
        return acc;
      }, {});

      state.frames = { ...state.frames, ...frames };
    },

    updateFrameSummary: (state: VideoFrameState, action: PayloadAction<UIFrameSummary>) => {
      const { stateId, frameKey } = action.payload;
      state.frameSummaries[[stateId, frameKey].join('#')] = action.payload;
    },

    selectSummary: (state: VideoFrameState, action: PayloadAction<string>) => {
      state.selectedSummary = action.payload;
    },
  },
});

export const selectVideoFrame = (root: RootState) => root.videoFrames;

export const VideoFramesAction = VideoFrameSlice.actions;
export const VideoFrameReducer = VideoFrameSlice.reducer;
export const VideoFrameSelector = createSelector([selectVideoFrame], (frameState: VideoFrameState) => ({
  frameKeys: (chunkId: string) =>
    frameState.selectedSummary
      ? Object.values(frameState.frames)
          .filter((el) => el.stateId == frameState.selectedSummary && el.chunkId == chunkId)
          .map((curr) => [curr.stateId, curr.chunkId, curr.frameId].join('#'))
      : [],
  frameSummaries: Object.values(frameState.frameSummaries)
    .filter((el) => el.stateId == frameState.selectedSummary)
    .sort((a, b) => +a.startFrame - +b.startFrame),

  frameSummaryStatusCount: Object.values(frameState.frameSummaries)
    .filter((el) => el.stateId == frameState.selectedSummary)
    .reduce(
      (acc: CountStatus, curr: UIFrameSummary) => {
        acc[curr.status] += 1;
        return acc;
      },
      { ready: 0, inProgress: 0, complete: 0, na: 0 },
    ),

  frameSummaryStatus: (chunkId: string) => {
    let response: ChunkSummaryStatusFromFrames = {
      summaryUsingFrames: 0,
      summaries: [],
      summaryStatus: StateActionStatus.NA,
    };

    const frames = (
      frameState.selectedSummary ? Object.values(frameState.frames).filter((el) => el.chunkId === chunkId) : []
    ).sort((a, b) => +a.frameId - +b.frameId);

    if (frames.length > 0) {
      const firstFrame = frames[0];
      const lastFrame = frames[frames.length - 1];

      const relevantSumms = Object.values(frameState.frameSummaries).filter(
        (el) =>
          (+firstFrame.frameId >= +el.startFrame && +firstFrame <= +el.endFrame) ||
          (+lastFrame.frameId >= +el.startFrame && +lastFrame.frameId <= +el.endFrame),
      );

      for (const summ of relevantSumms) {
        if (summ.status !== StateActionStatus.COMPLETE) {
          response.summaryUsingFrames += 1;
        }

        if (summ.summary) {
          response.summaries.push({
            summary: summ.summary,
            status: summ.status,
            frames: summ.frames,
          });
        }
      }
    }

    console.log(response);

    return response;
  },

  frames: Object.values(frameState.frames)
    .filter((el) => el.stateId === frameState.selectedSummary)
    .sort((a, b) => +a.frameId - +b.frameId),
  frameData: (frameKey: string) => {
    return frameState.frames[frameKey] ?? null;
  },
}));
