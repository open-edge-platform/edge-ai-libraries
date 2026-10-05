// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { configureStore } from '@reduxjs/toolkit';
import { render, screen, waitFor } from '@testing-library/react';
import { ReactNode } from 'react';
import { Provider } from 'react-redux';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import LiveStreamModal from '../components/LiveStreams/LiveStreamModal';
import { LiveStream, LiveStreamState } from '../redux/streams/streams';
import { StreamsActions, StreamsReducers } from '../redux/streams/streamsSlice';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const socketMock = {
  emit: vi.fn(),
  on: vi.fn(),
  off: vi.fn(),
  connected: true,
};
vi.mock('../socket', () => ({
  socket: {
    emit: (...args: unknown[]) => socketMock.emit(...args),
    on: (...args: unknown[]) => socketMock.on(...args),
    off: (...args: unknown[]) => socketMock.off(...args),
    get connected() {
      return socketMock.connected;
    },
  },
}));

vi.mock('../components/Notification/notify', () => ({
  NotificationSeverity: { SUCCESS: 'success', ERROR: 'error' },
  notify: vi.fn(),
}));

const mockList = vi.fn();
vi.mock('../redux/streams/streamsApi', () => ({
  streamsApi: {
    list: (...args: unknown[]) => mockList(...args),
    createStream: vi.fn(),
    updateStream: vi.fn(),
    deleteStream: vi.fn(),
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
  state: LiveStreamState.RUNNING,
  frame_interval: 15,
  enable_object_detection: false,
  detection_confidence: 0.5,
  tags: ['lobby'],
  stats: {
    frames_processed: 10,
    embeddings_created: 2,
    segments_stored: 0,
    frames_stored: 0,
    reconnect_count: 0,
  },
  ...overrides,
});

const makeStore = () =>
  configureStore({ reducer: { streams: StreamsReducers } });

const wrap = (node: ReactNode, store = makeStore()) => ({
  store,
  ...render(<Provider store={store}>{node}</Provider>),
});

beforeEach(() => {
  vi.clearAllMocks();
  socketMock.connected = true;
  mockList.mockResolvedValue({ count: 0, streams: [] });
});

afterEach(() => {
  vi.useRealTimers();
});

describe('LiveStreamModal', () => {
  it('does nothing while closed', () => {
    wrap(<LiveStreamModal open={false} onClose={vi.fn()} />);

    expect(socketMock.emit).not.toHaveBeenCalled();
    expect(mockList).not.toHaveBeenCalled();
  });

  it('subscribes to the streams room and loads on open', async () => {
    wrap(<LiveStreamModal open onClose={vi.fn()} />);

    expect(socketMock.emit).toHaveBeenCalledWith('streams:subscribe');
    await waitFor(() => expect(mockList).toHaveBeenCalled());
  });

  it('unsubscribes on unmount so the server stops polling dataprep', () => {
    const { unmount } = wrap(<LiveStreamModal open onClose={vi.fn()} />);

    unmount();

    expect(socketMock.emit).toHaveBeenCalledWith('streams:unsubscribe');
  });

  it('unsubscribes when the modal closes without unmounting', async () => {
    const { rerender, store } = wrap(
      <LiveStreamModal open onClose={vi.fn()} />,
    );

    rerender(
      <Provider store={store}>
        <LiveStreamModal open={false} onClose={vi.fn()} />
      </Provider>,
    );

    expect(socketMock.emit).toHaveBeenCalledWith('streams:unsubscribe');
  });

  it('does not poll while the socket is connected', async () => {
    vi.useFakeTimers();
    wrap(<LiveStreamModal open onClose={vi.fn()} />);

    const initialCalls = mockList.mock.calls.length;
    vi.advanceTimersByTime(20000);

    // The socket broadcast is the freshness source; the interval is only a
    // fallback.
    expect(mockList.mock.calls.length).toBe(initialCalls);
  });

  it('falls back to polling when the socket is down', () => {
    vi.useFakeTimers();
    socketMock.connected = false;
    wrap(<LiveStreamModal open onClose={vi.fn()} />);

    const initialCalls = mockList.mock.calls.length;
    vi.advanceTimersByTime(11000);

    expect(mockList.mock.calls.length).toBeGreaterThan(initialCalls);
  });

  it('starts polling when the socket drops while the modal is open', () => {
    vi.useFakeTimers();
    wrap(<LiveStreamModal open onClose={vi.fn()} />);

    vi.advanceTimersByTime(10000);
    const beforeDrop = mockList.mock.calls.length;

    // The interval checks `socket.connected` per tick rather than being
    // installed conditionally, so a mid-session drop is covered.
    socketMock.connected = false;
    vi.advanceTimersByTime(6000);

    expect(mockList.mock.calls.length).toBeGreaterThan(beforeDrop);
  });

  it('shows the empty state when no streams are registered', async () => {
    wrap(<LiveStreamModal open onClose={vi.fn()} />);

    await waitFor(() =>
      expect(screen.getByText('noStreamsAvailable')).toBeTruthy(),
    );
  });

  it('renders registered streams', async () => {
    mockList.mockResolvedValue({ count: 1, streams: [makeStream()] });
    const store = makeStore();
    store.dispatch(StreamsActions.streamsSync([makeStream()]));

    wrap(<LiveStreamModal open onClose={vi.fn()} />, store);

    await waitFor(() => expect(screen.getByText('lobby-cam')).toBeTruthy());
  });

  it('distinguishes an empty filter result from an empty registry', async () => {
    mockList.mockResolvedValue({ count: 1, streams: [makeStream()] });
    const store = makeStore();

    const { container } = wrap(
      <LiveStreamModal open onClose={vi.fn()} />,
      store,
    );
    await waitFor(() => expect(screen.getByText('lobby-cam')).toBeTruthy());

    const search = container.querySelector(
      '#stream-tag-filter',
    ) as HTMLInputElement;
    const { fireEvent } = await import('@testing-library/react');
    fireEvent.change(search, { target: { value: 'nothing-matches' } });

    await waitFor(() =>
      expect(screen.getByText('noStreamsMatchFilter')).toBeTruthy(),
    );
    expect(screen.queryByText('noStreamsAvailable')).toBeNull();
  });

  // StreamFormModal seeds its state once per mount, so LiveStreamModal must
  // pass a `key` that changes with the edited stream. Without it, editing a
  // second camera would silently show the first camera's values.
  it('repopulates the edit form when a different stream is edited', async () => {
    const second = makeStream({
      stream_id: 'stream-2',
      stream_name: 'dock-cam',
      stream_url: 'rtsp://cam-2:554/live',
    });
    mockList.mockResolvedValue({ count: 2, streams: [makeStream(), second] });

    const { fireEvent } = await import('@testing-library/react');
    wrap(<LiveStreamModal open onClose={vi.fn()} />);
    await waitFor(() => expect(screen.getByText('lobby-cam')).toBeTruthy());

    const openEdit = (streamId: string) => {
      fireEvent.click(screen.getByTestId(`stream-edit-${streamId}`));
    };

    openEdit('stream-1');
    await waitFor(() =>
      expect(screen.getByTestId('stream-url-readonly').textContent).toBe(
        'rtsp://cam-1:554/live',
      ),
    );

    const formModal = screen
      .getByTestId('stream-url-readonly')
      .closest('.cds--modal') as HTMLElement;
    fireEvent.click(
      Array.from(formModal.querySelectorAll('button')).find(
        (button) => button.textContent === 'cancel',
      ) as Element,
    );
    openEdit('stream-2');

    await waitFor(() =>
      expect(screen.getByTestId('stream-url-readonly').textContent).toBe(
        'rtsp://cam-2:554/live',
      ),
    );
  });

  // Carbon's OverflowMenu portals its options into document.body at
  // `z-index: 6000`, which paints below this modal - the menu opened but was
  // invisible and unclickable. Row actions must stay inline buttons.
  it('exposes row actions as inline buttons, not a portalled overflow menu', async () => {
    mockList.mockResolvedValue({ count: 1, streams: [makeStream()] });

    const { fireEvent } = await import('@testing-library/react');
    wrap(<LiveStreamModal open onClose={vi.fn()} />);
    await waitFor(() => expect(screen.getByText('lobby-cam')).toBeTruthy());

    expect(document.querySelector('.cds--overflow-menu')).toBeNull();

    const row = screen.getByTestId('stream-row-stream-1');
    for (const action of ['toggle', 'edit', 'delete']) {
      const button = screen.getByTestId(`stream-${action}-stream-1`);
      expect(row.contains(button)).toBe(true);
    }

    // The delete action reaches its confirmation dialog.
    fireEvent.click(screen.getByTestId('stream-delete-stream-1'));
    await waitFor(() =>
      expect(screen.getByText('confirmDeleteStreamBody')).toBeTruthy(),
    );
  });

  // Two visible Carbon modals fight over focus: the list modal's focus trap
  // drags focus out of the child's inputs, and because it is `passiveModal`
  // every click inside the child counts as a click-outside and tries to close
  // it. The list must therefore be hidden while a child modal is open.
  it('hides the stream list while the add/edit form is open', async () => {
    mockList.mockResolvedValue({ count: 1, streams: [makeStream()] });

    const { fireEvent } = await import('@testing-library/react');
    wrap(<LiveStreamModal open onClose={vi.fn()} />);
    await waitFor(() => expect(screen.getByText('lobby-cam')).toBeTruthy());

    const listModal = screen
      .getByText('liveStreamsDescription')
      .closest('.cds--modal') as HTMLElement;
    expect(listModal.classList.contains('is-visible')).toBe(true);

    // `addStream` also names the form modal's primary button once mounted.
    fireEvent.click(screen.getByTestId('add-stream-button'));

    await waitFor(() =>
      expect(screen.getByTestId('stream-url-input')).toBeTruthy(),
    );
    const formModal = screen
      .getByTestId('stream-url-input')
      .closest('.cds--modal') as HTMLElement;

    expect(formModal.classList.contains('is-visible')).toBe(true);
    expect(listModal.classList.contains('is-visible')).toBe(false);

    // Closing the child brings the list back.
    fireEvent.click(
      Array.from(formModal.querySelectorAll('button')).find(
        (button) => button.textContent === 'cancel',
      ) as Element,
    );
    await waitFor(() =>
      expect(listModal.classList.contains('is-visible')).toBe(true),
    );
  });

  it('surfaces a load error inline rather than silently showing an empty list', async () => {
    mockList.mockRejectedValue(new Error('dataprep down'));

    wrap(<LiveStreamModal open onClose={vi.fn()} />);

    await waitFor(() =>
      expect(screen.getByText('Unable to load live streams.')).toBeTruthy(),
    );
  });
});
