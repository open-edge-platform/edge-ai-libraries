// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import axios from 'axios';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { LiveStreamState } from '../redux/streams/streams';
import { streamErrorMessage, streamsApi } from '../redux/streams/streamsApi';

vi.mock('axios', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
    isAxiosError: vi.fn(),
  },
}));

vi.mock('../config', () => ({
  APP_URL: 'http://localhost:3000',
}));

const mockedAxios = axios as unknown as {
  get: ReturnType<typeof vi.fn>;
  post: ReturnType<typeof vi.fn>;
  patch: ReturnType<typeof vi.fn>;
  delete: ReturnType<typeof vi.fn>;
  isAxiosError: ReturnType<typeof vi.fn>;
};

describe('streamsApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('list', () => {
    it('requests the bare collection URL when no filters are given', async () => {
      mockedAxios.get.mockResolvedValue({ data: { count: 0, streams: [] } });

      await streamsApi.list();

      expect(mockedAxios.get).toHaveBeenCalledWith(
        'http://localhost:3000/streams',
      );
    });

    it('omits an empty state filter rather than sending state=', async () => {
      mockedAxios.get.mockResolvedValue({ data: { count: 0, streams: [] } });

      await streamsApi.list({ state: '' });

      // An empty `state` query value would be rejected by the backend enum
      // rather than being treated as "no filter".
      expect(mockedAxios.get).toHaveBeenCalledWith(
        'http://localhost:3000/streams',
      );
    });

    it('serializes the tag filter as a repeated `tags` key', async () => {
      mockedAxios.get.mockResolvedValue({ data: { count: 0, streams: [] } });

      await streamsApi.list({
        state: LiveStreamState.RUNNING,
        tag: 'lobby',
      });

      const url = mockedAxios.get.mock.calls[0][0] as string;
      // FastAPI binds List[str] from repeated keys. `tags[]=` is silently
      // ignored, which would make the filter appear to do nothing.
      expect(url).toContain('tags=lobby');
      expect(url).not.toContain('tags%5B%5D');
      expect(url).toContain('state=running');
    });
  });

  describe('createStream', () => {
    it('unwraps the stream from the response envelope', async () => {
      mockedAxios.post.mockResolvedValue({
        data: { stream: { stream_id: 'abc', stream_url: 'rtsp://cam:554/s' } },
      });

      const created = await streamsApi.createStream({
        stream_url: 'rtsp://user:secret@cam:554/s',
      });

      expect(created.stream_id).toBe('abc');
      // The caller gets back the backend's redacted URL, not its own input.
      expect(created.stream_url).toBe('rtsp://cam:554/s');
    });

    it('is a plain function, not a redux thunk', () => {
      // A `createAsyncThunk` would expose the credentialed URL on the
      // dispatched action's `meta.arg`. Guard the shape so a future
      // refactor to a thunk fails loudly here.
      expect(streamsApi.createStream).not.toHaveProperty('pending');
      expect(streamsApi.createStream).not.toHaveProperty('fulfilled');
      expect(streamsApi.createStream).not.toHaveProperty('typePrefix');
    });
  });

  describe('updateStream', () => {
    it('PATCHes the encoded stream id', async () => {
      mockedAxios.patch.mockResolvedValue({
        data: { stream: { stream_id: 'a/b' } },
      });

      await streamsApi.updateStream('a/b', { stream_name: 'x' });

      expect(mockedAxios.patch).toHaveBeenCalledWith(
        'http://localhost:3000/streams/a%2Fb',
        { stream_name: 'x' },
      );
    });
  });

  describe('setState', () => {
    it('sends the state as an update payload', async () => {
      mockedAxios.patch.mockResolvedValue({
        data: { stream: { stream_id: 'abc' } },
      });

      await streamsApi.setState('abc', LiveStreamState.PAUSED);

      expect(mockedAxios.patch).toHaveBeenCalledWith(
        'http://localhost:3000/streams/abc',
        { state: 'paused' },
      );
    });
  });

  describe('deleteStream', () => {
    it('defaults both purge flags to false', async () => {
      mockedAxios.delete.mockResolvedValue({ data: {} });

      await streamsApi.deleteStream('abc');

      const url = mockedAxios.delete.mock.calls[0][0] as string;
      expect(url).toContain('purge_embeddings=false');
      expect(url).toContain('purge_media=false');
    });

    it('passes the purge flags through when set', async () => {
      mockedAxios.delete.mockResolvedValue({ data: {} });

      await streamsApi.deleteStream('abc', {
        purge_embeddings: true,
        purge_media: true,
      });

      const url = mockedAxios.delete.mock.calls[0][0] as string;
      expect(url).toContain('purge_embeddings=true');
      expect(url).toContain('purge_media=true');
    });
  });
});

describe('streamErrorMessage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns the fallback for a non-axios error', () => {
    mockedAxios.isAxiosError.mockReturnValue(false);

    expect(streamErrorMessage(new Error('boom'), 'fallback')).toBe('fallback');
  });

  it('prefers the backend `message` field', () => {
    mockedAxios.isAxiosError.mockReturnValue(true);

    const error = { response: { data: { message: 'Stream limit reached' } } };

    expect(streamErrorMessage(error, 'fallback')).toBe('Stream limit reached');
  });

  it('joins an array of validation messages', () => {
    mockedAxios.isAxiosError.mockReturnValue(true);

    const error = {
      response: { data: { message: ['url invalid', 'name required'] } },
    };

    expect(streamErrorMessage(error, 'fallback')).toBe(
      'url invalid; name required',
    );
  });

  it('falls back to FastAPI `detail` when `message` is absent', () => {
    mockedAxios.isAxiosError.mockReturnValue(true);

    const error = { response: { data: { detail: 'Not found' } } };

    expect(streamErrorMessage(error, 'fallback')).toBe('Not found');
  });

  it('uses the fallback when the body carries no usable text', () => {
    mockedAxios.isAxiosError.mockReturnValue(true);

    expect(streamErrorMessage({ response: { data: {} } }, 'fallback')).toBe(
      'fallback',
    );
    expect(streamErrorMessage({ response: { data: { message: '' } } }, 'fb')).toBe(
      'fb',
    );
  });
});
