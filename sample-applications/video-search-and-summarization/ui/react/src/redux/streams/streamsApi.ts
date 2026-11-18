// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import axios from 'axios';
import { APP_URL } from '../../config';
import {
  LiveStream,
  LiveStreamCreatePayload,
  LiveStreamFilters,
  LiveStreamListRO,
  LiveStreamPurgeOptions,
  LiveStreamRO,
  LiveStreamState,
  LiveStreamUpdatePayload,
} from './streams';

const base = () => `${APP_URL}/streams`;

/**
 * Direct HTTP access to the live-stream API.
 *
 * `createStream` is deliberately NOT wrapped in a `createAsyncThunk`.
 * `createAsyncThunk` records its argument on the dispatched action's
 * `meta.arg`, and the create argument contains an RTSP URL that may embed
 * `user:password`. Any action log - Redux DevTools, a logging middleware, an
 * error reporter that serializes actions - would then capture the credential.
 *
 * The form component calls this directly and dispatches only the response,
 * whose `stream_url` the backend has already redacted.
 */
export const streamsApi = {
  async list(filters: LiveStreamFilters = {}): Promise<LiveStreamListRO> {
    const params = new URLSearchParams();
    if (filters.state) params.set('state', filters.state);
    if (filters.tag) params.append('tags', filters.tag);

    const query = params.toString();
    const { data } = await axios.get<LiveStreamListRO>(
      query ? `${base()}?${query}` : base(),
    );
    return data;
  },

  async createStream(payload: LiveStreamCreatePayload): Promise<LiveStream> {
    const { data } = await axios.post<LiveStreamRO>(base(), payload);
    return data.stream;
  },

  async updateStream(
    streamId: string,
    payload: LiveStreamUpdatePayload,
  ): Promise<LiveStream> {
    const { data } = await axios.patch<LiveStreamRO>(
      `${base()}/${encodeURIComponent(streamId)}`,
      payload,
    );
    return data.stream;
  },

  async setState(
    streamId: string,
    state: LiveStreamState.RUNNING | LiveStreamState.PAUSED,
  ): Promise<LiveStream> {
    return streamsApi.updateStream(streamId, { state });
  },

  async deleteStream(
    streamId: string,
    purge: LiveStreamPurgeOptions = {},
  ): Promise<void> {
    const params = new URLSearchParams({
      purge_embeddings: String(purge.purge_embeddings ?? false),
      purge_media: String(purge.purge_media ?? false),
    });
    await axios.delete(
      `${base()}/${encodeURIComponent(streamId)}?${params.toString()}`,
    );
  },
};

/**
 * Pull a human-usable message out of an axios failure.
 *
 * The backend sends the concurrency-cap explanation and the URL-validation
 * reason in `message`; showing a bare "Request failed with status code 503"
 * instead would leave the user with no idea what to do.
 */
export const streamErrorMessage = (error: unknown, fallback: string): string => {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data as
      | { message?: string | string[]; detail?: string }
      | undefined;
    const message = data?.message ?? data?.detail;
    if (Array.isArray(message)) return message.join('; ');
    if (typeof message === 'string' && message.length > 0) return message;
  }
  return fallback;
};
