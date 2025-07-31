// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Injectable } from '@nestjs/common';
import {
  CountStatus,
  UIChunk,
  UIFrame,
  UIState,
  UIStateStatus,
} from '../models/uiState.model';
import { StateService } from './state.service';
import {
  FrameSummary,
  InferenceConfig,
  State,
  StateAudio,
} from '../models/state.model';

@Injectable()
export class UiService {
  constructor(private $state: StateService) {}

  getInferenceConfig(stateId: string, state?: State): InferenceConfig {
    if (!state) {
      state = this.$state.fetch(stateId);
    }

    let inferenceConfig: InferenceConfig = {};

    if (state) {
      inferenceConfig = { ...(state.inferenceConfig ?? {}) };
    }

    return inferenceConfig;
  }

  getSummaryData(stateId: string, frameKey: string): FrameSummary | null {
    const state = this.$state.fetch(stateId);
    return state?.frameSummaries[frameKey] ?? null;
  }

  getStateStatus(stateId: string, state?: State): UIStateStatus | null {
    if (!state) {
      state = this.$state.fetch(stateId);
    }

    if (state) {
      const statusData: UIStateStatus = {
        chunkingStatus: state.status.chunking,
        frameSummaryStatus: Object.values(state.frameSummaries).reduce(
          (acc: CountStatus, frameSummary) => {
            acc[frameSummary.status] += 1;
            return acc;
          },
          { complete: 0, inProgress: 0, na: 0, ready: 0 },
        ),
        videoSummaryStatus: state.status.summarizing,
      };

      return statusData;
    }

    return null;
  }

  getUIChunks(stateId: string, state?: State): UIChunk[] {
    if (!state) {
      state = this.$state.fetch(stateId);
    }

    if (state) {
      const uiChunks = Object.values(state.chunks)
        .map((chunk) => this.getUiChunk(stateId, chunk.chunkId, state)!)
        .sort((a, b) => +a.chunkId - +b.chunkId);

      if (uiChunks.length > 0) {
        uiChunks[uiChunks.length - 1].duration.to = -1;
      }

      return uiChunks;
    }

    return [];
  }

  getUiChunk(stateId: string, chunkId: string, state?: State): UIChunk | null {
    if (!state) {
      state = this.$state.fetch(stateId);
    }

    if (state) {
      const chunk = state.chunks[chunkId];

      const userInputs = state.userInputs;

      if (chunk) {
        const chunkFrom = (+chunkId - 1) * userInputs.chunkDuration;

        const uiChunk: UIChunk = {
          chunkId,
          duration: {
            from: chunkFrom,
            to: chunkFrom + userInputs.chunkDuration,
          },
        };

        return uiChunk;
      }
    }

    return null;
  }

  getAudioSettings(stateId: string, state?: State): StateAudio | null {
    if (!state) {
      state = this.$state.fetch(stateId);
    }
    if (state && state.audio) {
      const audioSettings: StateAudio = {
        device: state.audio.device,
        model: state.audio.model,
        status: state.audio.status,
        transcript: [],
      };
      if (state.audio.transcriptPath) {
        audioSettings.transcriptPath = state.audio.transcriptPath;
      }
      return audioSettings;
    }

    return null;
  }

  getUIFrames(stateId: string, state?: State): UIFrame[] {
    if (!state) {
      state = this.$state.fetch(stateId);
    }

    if (state) {
      return Object.values(state.frames)
        .map((frame) => this.getUiFrame(stateId, frame.frameId, state)!)
        .sort((a, b) => +a.frameId - +b.frameId);
    }

    return [];
  }

  getUiFrame(stateId: string, frameId: string, state?: State): UIFrame | null {
    if (!state) {
      state = this.$state.fetch(stateId);
    }

    if (state && state.frames[frameId]) {
      const frame = state.frames[frameId];

      const uiFrame: UIFrame = {
        chunkId: frame.chunkId,
        frameId: frame.frameId,
        url: frame.frameUri,
        videoTimeStamp: frame.metadata?.frame_timestamp ?? 0,
      };

      return uiFrame;
    }

    return null;
  }

  getUiState(stateId: string): UIState | null {
    const state = this.$state.fetch(stateId);

    if (state) {
      const uiState: UIState = {
        chunks: [],
        frames: [],
        stateId: state.stateId,
        title: state.title,
        userInputs: state.userInputs,
        frameSummaries: Object.values(state.frameSummaries).map((curr) => ({
          ...curr,
          stateId,
        })),
        videoId: state.video.videoId,
        summary: state.summary ?? '',
        systemConfig: state.systemConfig,
        chunkingStatus: state.status.chunking,
        inferenceConfig: this.getInferenceConfig(stateId, state),
        frameSummaryStatus: Object.values(state.frameSummaries).reduce(
          (acc: CountStatus, frameSummary) => {
            acc[frameSummary.status] += 1;
            return acc;
          },
          { complete: 0, inProgress: 0, na: 0, ready: 0 },
        ),
        videoSummaryStatus: state.status.summarizing,
      };

      if (state.userInputs) {
        uiState.userInputs = state.userInputs;
      }

      if (state.video) {
        uiState.videoId = state.video.videoId;
      }

      uiState.chunks = this.getUIChunks(stateId, state);
      uiState.frames = this.getUIFrames(stateId, state);

      return uiState;
    }

    return null;
  }
}
