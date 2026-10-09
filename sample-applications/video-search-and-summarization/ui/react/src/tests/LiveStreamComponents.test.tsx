// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { configureStore } from '@reduxjs/toolkit';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ReactNode } from 'react';
import { Provider } from 'react-redux';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import DeleteStreamConfirm from '../components/LiveStreams/DeleteStreamConfirm';
import StreamFormModal from '../components/LiveStreams/StreamFormModal';
import StreamRow from '../components/LiveStreams/StreamRow';
import StreamStateTag from '../components/LiveStreams/StreamStateTag';
import { LiveStream, LiveStreamState } from '../redux/streams/streams';
import { StreamsReducers } from '../redux/streams/streamsSlice';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const mockNotify = vi.fn();
vi.mock('../components/Notification/notify', () => ({
  NotificationSeverity: {
    SUCCESS: 'success',
    ERROR: 'error',
    WARNING: 'warning',
    INFO: 'info',
  },
  notify: (...args: unknown[]) => mockNotify(...args),
}));

const mockCreateStream = vi.fn();
const mockUpdateStream = vi.fn();
const mockDeleteStream = vi.fn();

vi.mock('../redux/streams/streamsApi', () => ({
  streamsApi: {
    list: vi.fn(async () => ({ count: 0, streams: [] })),
    createStream: (...args: unknown[]) => mockCreateStream(...args),
    updateStream: (...args: unknown[]) => mockUpdateStream(...args),
    deleteStream: (...args: unknown[]) => mockDeleteStream(...args),
    setState: vi.fn(),
  },
  streamErrorMessage: (_error: unknown, fallback: string) => fallback,
}));

vi.mock('../config', () => ({
  APP_URL: 'http://localhost:3000',
  ASSETS_ENDPOINT: '',
  SOCKET_APPEND: 'CONFIG_OFF',
  FEATURE_SUMMARY: 'FEATURE_OFF',
  FEATURE_SEARCH: 'FEATURE_ON',
  FEATURE_MUX: 'ATOMIC',
  FEATURE_CAMERA_CONFIG: 'FEATURE_OFF',
  FEATURE_LIVE_STREAMS: 'FEATURE_ON',
  NVR_API_BASE: '',
}));

const makeStream = (overrides: Partial<LiveStream> = {}): LiveStream => ({
  stream_id: 'stream-1',
  stream_url: 'rtsp://cam-1:554/live',
  stream_name: 'lobby-cam',
  description: 'front door',
  state: LiveStreamState.RUNNING,
  frame_interval: 15,
  enable_object_detection: false,
  detection_confidence: 0.5,
  tags: ['lobby'],
  stats: {
    frames_processed: 1234,
    embeddings_created: 56,
    segments_stored: 2,
    frames_stored: 10,
    reconnect_count: 0,
    uptime_seconds: 3725,
  },
  ...overrides,
});

const store = () => configureStore({ reducer: { streams: StreamsReducers } });

const wrap = (node: ReactNode, s = store()) =>
  render(<Provider store={s}>{node}</Provider>);

beforeEach(() => {
  vi.clearAllMocks();
});

describe('StreamStateTag', () => {
  it.each([
    [LiveStreamState.PENDING, 'streamStatePending'],
    [LiveStreamState.STARTING, 'streamStateStarting'],
    [LiveStreamState.RUNNING, 'streamStateRunning'],
    [LiveStreamState.PAUSED, 'streamStatePaused'],
    [LiveStreamState.RECONNECTING, 'streamStateReconnecting'],
    [LiveStreamState.ERROR, 'streamStateError'],
    [LiveStreamState.STOPPED, 'streamStateStopped'],
  ])('renders a label for %s', (state, labelKey) => {
    render(<StreamStateTag state={state} />);

    expect(screen.getByText(labelKey)).toBeTruthy();
  });

  it('renders the raw value for an unmapped state instead of a blank tag', () => {
    // A backend adding an eighth state must not produce an empty badge that
    // looks like a UI fault.
    render(<StreamStateTag state={'quiescing' as LiveStreamState} />);

    expect(screen.getByText('quiescing')).toBeTruthy();
  });
});

describe('StreamRow', () => {
  const handlers = {
    onEdit: vi.fn(),
    onDelete: vi.fn(),
    onToggleState: vi.fn(),
  };

  it('shows the name, redacted url and stats', () => {
    render(<StreamRow stream={makeStream()} {...handlers} />);

    expect(screen.getByText('lobby-cam')).toBeTruthy();
    expect(screen.getByText('rtsp://cam-1:554/live')).toBeTruthy();
    expect(screen.getByTestId('stream-row-stream-1')).toBeTruthy();
  });

  it('formats uptime as hours and minutes', () => {
    render(<StreamRow stream={makeStream()} {...handlers} />);

    // 3725s = 1h 2m
    expect(screen.getByText(/1h 2m/)).toBeTruthy();
  });

  it('surfaces last_error only in the error state', () => {
    const { rerender } = render(
      <StreamRow
        stream={makeStream({ last_error: 'connection refused' })}
        {...handlers}
      />,
    );
    expect(screen.queryByText('connection refused')).toBeNull();

    rerender(
      <StreamRow
        stream={makeStream({
          state: LiveStreamState.ERROR,
          last_error: 'connection refused',
        })}
        {...handlers}
      />,
    );
    expect(screen.getByText('connection refused')).toBeTruthy();
  });

  it('tolerates a stream with no stats block', () => {
    // The poller can emit a freshly registered stream before the worker has
    // reported anything.
    render(
      <StreamRow
        stream={makeStream({ stats: undefined as never })}
        {...handlers}
      />,
    );

    expect(screen.getByText('lobby-cam')).toBeTruthy();
  });
});

describe('StreamFormModal', () => {
  it('renders an editable url input when creating', () => {
    wrap(<StreamFormModal open onClose={vi.fn()} />);

    expect(screen.getByTestId('stream-url-input')).toBeTruthy();
    expect(screen.queryByTestId('stream-url-readonly')).toBeNull();
  });

  it('renders the url as read-only text when editing', () => {
    // The update API has no stream_url field, so an editable control could
    // never apply the change.
    wrap(<StreamFormModal open stream={makeStream()} onClose={vi.fn()} />);

    expect(screen.getByTestId('stream-url-readonly').textContent).toBe(
      'rtsp://cam-1:554/live',
    );
    expect(screen.queryByTestId('stream-url-input')).toBeNull();
  });

  it('creates via the api module, not a redux thunk', async () => {
    mockCreateStream.mockResolvedValue(makeStream({ stream_id: 'new' }));
    const onClose = vi.fn();
    const s = store();

    wrap(<StreamFormModal open onClose={onClose} />, s);

    fireEvent.change(screen.getByTestId('stream-url-input'), {
      target: { value: 'rtsp://user:secret@cam-9:554/live' },
    });
    fireEvent.change(screen.getByTestId('stream-name-input'), {
      target: { value: 'garage' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'addStream' }));

    await waitFor(() => expect(mockCreateStream).toHaveBeenCalled());

    expect(mockCreateStream.mock.calls[0][0]).toMatchObject({
      stream_url: 'rtsp://user:secret@cam-9:554/live',
      stream_name: 'garage',
    });

    // Only the backend's redacted response reaches the store.
    await waitFor(() =>
      expect(s.getState().streams.streams).toHaveLength(1),
    );
    expect(JSON.stringify(s.getState().streams)).not.toContain('secret');
    expect(onClose).toHaveBeenCalled();
  });

  it('refuses to submit a non-rtsp url', async () => {
    wrap(<StreamFormModal open onClose={vi.fn()} />);

    const urlInput = screen.getByTestId('stream-url-input');
    fireEvent.change(urlInput, { target: { value: 'http://cam-9/live' } });
    fireEvent.change(screen.getByTestId('stream-name-input'), {
      target: { value: 'garage' },
    });
    // Leaving the field surfaces the validation message.
    fireEvent.blur(urlInput);

    await waitFor(() =>
      expect(screen.getByText('streamUrlInvalid')).toBeTruthy(),
    );
    // The submit button stays disabled for malformed input, so the stream can
    // never be created from an invalid URL.
    expect(
      (screen.getByRole('button', { name: 'addStream' }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    expect(mockCreateStream).not.toHaveBeenCalled();
  });

  it('clears the url error once the field is emptied', async () => {
    wrap(<StreamFormModal open onClose={vi.fn()} />);

    const urlInput = screen.getByTestId('stream-url-input');
    fireEvent.change(urlInput, { target: { value: 'http://cam-9/live' } });
    fireEvent.blur(urlInput);

    await waitFor(() =>
      expect(screen.getByText('streamUrlInvalid')).toBeTruthy(),
    );

    // Clearing the input is "incomplete", not "invalid": the error must go away
    // instead of sticking until a valid URL is pasted.
    fireEvent.change(urlInput, { target: { value: '' } });

    await waitFor(() =>
      expect(screen.queryByText('streamUrlInvalid')).toBeNull(),
    );
    // Still not submittable while empty.
    expect(
      (screen.getByRole('button', { name: 'addStream' }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  });

  // The URL is the only field the ingestion API requires: the name falls back
  // to the redacted URL server-side, so the form must not demand one.
  it('submits with only a URL, omitting the optional name', async () => {
    mockCreateStream.mockResolvedValue(makeStream());

    wrap(<StreamFormModal open onClose={vi.fn()} />);

    fireEvent.change(screen.getByTestId('stream-url-input'), {
      target: { value: 'rtsp://cam-9:554/live' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'addStream' }));

    await waitFor(() => expect(mockCreateStream).toHaveBeenCalled());
    const payload = mockCreateStream.mock.calls[0][0];
    expect(payload.stream_url).toBe('rtsp://cam-9:554/live');
    expect('stream_name' in payload).toBe(false);
  });

  // These must match multimodal-dataprep's FRAME_INTERVAL / ENABLE_OBJECT_DETECTION
  // / DETECTION_CONFIDENCE defaults. The form always sends them, so a mismatch
  // silently overrides the service's own configuration.
  it('submits the service default frame interval and detection confidence', async () => {
    mockCreateStream.mockResolvedValue(makeStream());

    wrap(<StreamFormModal open onClose={vi.fn()} />);

    fireEvent.change(screen.getByTestId('stream-url-input'), {
      target: { value: 'rtsp://cam-9:554/live' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'addStream' }));

    await waitFor(() => expect(mockCreateStream).toHaveBeenCalled());
    const payload = mockCreateStream.mock.calls[0][0];
    expect(payload.frame_interval).toBe(15);
    expect(payload.detection_confidence).toBe(0.85);
  });

  it('enables object detection by default on a new stream', async () => {
    mockCreateStream.mockResolvedValue(makeStream());

    const { container } = wrap(<StreamFormModal open onClose={vi.fn()} />);

    const checkbox = container.querySelector<HTMLInputElement>(
      '#stream-enable-detection',
    );
    expect(checkbox?.checked).toBe(true);

    fireEvent.change(screen.getByTestId('stream-url-input'), {
      target: { value: 'rtsp://cam-9:554/live' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'addStream' }));

    await waitFor(() => expect(mockCreateStream).toHaveBeenCalled());
    expect(mockCreateStream.mock.calls[0][0].enable_object_detection).toBe(true);
  });

  it('sends an update payload with no stream_url when editing', async () => {
    mockUpdateStream.mockResolvedValue(makeStream({ stream_name: 'renamed' }));
    const s = store();

    wrap(<StreamFormModal open stream={makeStream()} onClose={vi.fn()} />, s);

    fireEvent.change(screen.getByTestId('stream-name-input'), {
      target: { value: 'renamed' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'editStream' }));

    await waitFor(() => expect(mockUpdateStream).toHaveBeenCalled());

    const [streamId, payload] = mockUpdateStream.mock.calls[0];
    expect(streamId).toBe('stream-1');
    expect(payload).not.toHaveProperty('stream_url');
    expect(payload.stream_name).toBe('renamed');
  });

  it('reports a create failure without closing the form', async () => {
    mockCreateStream.mockRejectedValue(new Error('limit reached'));
    const onClose = vi.fn();

    wrap(<StreamFormModal open onClose={onClose} />);

    fireEvent.change(screen.getByTestId('stream-url-input'), {
      target: { value: 'rtsp://cam-9:554/live' },
    });
    fireEvent.change(screen.getByTestId('stream-name-input'), {
      target: { value: 'garage' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'addStream' }));

    await waitFor(() => expect(mockNotify).toHaveBeenCalled());
    expect(mockNotify.mock.calls[0][1]).toBe('error');
    expect(onClose).not.toHaveBeenCalled();
  });

  // The form has no reset effect: it seeds state once per mount and relies on
  // LiveStreamModal passing a `key` derived from the edited stream id. This
  // test reproduces that contract so a regression in either half is caught.
  it('repopulates the form when the edited stream changes', () => {
    const { rerender } = wrap(
      <StreamFormModal
        key='form-stream-1'
        open
        stream={makeStream()}
        onClose={vi.fn()}
      />,
    );

    rerender(
      <Provider store={store()}>
        <StreamFormModal
          key='form-stream-2'
          open
          stream={makeStream({
            stream_id: 'stream-2',
            stream_name: 'dock-cam',
            stream_url: 'rtsp://cam-2:554/live',
          })}
          onClose={vi.fn()}
        />
      </Provider>,
    );

    expect(screen.getByTestId('stream-url-readonly').textContent).toBe(
      'rtsp://cam-2:554/live',
    );
  });
});

describe('DeleteStreamConfirm', () => {
  it('stays closed when no stream is selected', () => {
    // Carbon keeps the modal markup mounted and toggles `is-visible`, so
    // query for the open state rather than for the body text.
    const { container } = wrap(
      <DeleteStreamConfirm stream={null} onClose={vi.fn()} />,
    );

    expect(container.querySelector('.cds--modal.is-visible')).toBeNull();
  });

  it('opens once a stream is selected', () => {
    const { container } = wrap(
      <DeleteStreamConfirm stream={makeStream()} onClose={vi.fn()} />,
    );

    expect(container.querySelector('.cds--modal.is-visible')).not.toBeNull();
  });

  it('retains footage by default', async () => {
    mockDeleteStream.mockResolvedValue(undefined);
    const s = store();

    wrap(<DeleteStreamConfirm stream={makeStream()} onClose={vi.fn()} />, s);
    fireEvent.click(screen.getByRole('button', { name: 'deleteStream' }));

    await waitFor(() => expect(mockDeleteStream).toHaveBeenCalled());
    expect(mockDeleteStream.mock.calls[0][1]).toEqual({
      purge_embeddings: false,
      purge_media: false,
    });
  });

  it('sets both purge flags from the single checkbox', async () => {
    mockDeleteStream.mockResolvedValue(undefined);

    wrap(<DeleteStreamConfirm stream={makeStream()} onClose={vi.fn()} />);
    fireEvent.click(screen.getByTestId('purge-stream-data'));
    fireEvent.click(screen.getByRole('button', { name: 'deleteStream' }));

    await waitFor(() => expect(mockDeleteStream).toHaveBeenCalled());
    expect(mockDeleteStream.mock.calls[0][1]).toEqual({
      purge_embeddings: true,
      purge_media: true,
    });
  });

  it('keeps the dialog open when the delete fails', async () => {
    mockDeleteStream.mockRejectedValue(new Error('boom'));
    const onClose = vi.fn();

    wrap(<DeleteStreamConfirm stream={makeStream()} onClose={onClose} />);
    fireEvent.click(screen.getByRole('button', { name: 'deleteStream' }));

    await waitFor(() => expect(mockNotify).toHaveBeenCalled());
    expect(onClose).not.toHaveBeenCalled();
  });
});
