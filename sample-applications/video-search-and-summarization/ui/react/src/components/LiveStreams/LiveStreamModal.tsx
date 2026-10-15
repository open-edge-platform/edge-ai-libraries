// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Button, Dropdown, InlineNotification, Loading, Modal, Search } from '@carbon/react';
import { Add, Renew } from '@carbon/icons-react';
import { FC, useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSelector } from 'react-redux';
import styled from 'styled-components';
import { socket } from '../../socket';
import { useAppDispatch } from '../../redux/store';
import { LiveStream, LiveStreamState } from '../../redux/streams/streams';
import { StateActionStatus } from '../../redux/summary/summary';
import {
  StreamsActions,
  streamUpdate,
  streamsLoad,
  streamsSelector,
} from '../../redux/streams/streamsSlice';
import { NotificationSeverity, notify } from '../Notification/notify';
import DeleteStreamConfirm from './DeleteStreamConfirm';
import StreamFormModal from './StreamFormModal';
import StreamList from './StreamList';

const StyledModal = styled(Modal)`
  z-index: 8000 !important;

  & .cds--modal-container {
    z-index: 8000 !important;
  }
`;

const Description = styled.p`
  margin-bottom: 0.5rem;
`;

const Toolbar = styled.div`
  display: flex;
  align-items: flex-end;
  gap: 0.5rem;
  margin: 1rem 0;
  flex-wrap: wrap;
`;

const FilterCell = styled.div`
  min-width: 11rem;
`;

const Spacer = styled.div`
  flex: 1;
`;

const EmptyState = styled.div`
  padding: 2.5rem 1rem;
  text-align: center;
  border: 1px solid var(--cds-border-subtle, #e0e0e0);
`;

const EmptyTitle = styled.p`
  font-weight: 600;
  margin-bottom: 0.25rem;
`;

const Muted = styled.p`
  color: var(--cds-text-secondary, #525252);
`;

const Centered = styled.div`
  display: flex;
  justify-content: center;
  padding: 2.5rem 0;
`;

/** Fallback poll cadence used only while the socket is down. */
const FALLBACK_POLL_MS = 5000;

/** States from which pausing is the meaningful toggle. */
const PAUSABLE = [
  LiveStreamState.RUNNING,
  LiveStreamState.STARTING,
  LiveStreamState.RECONNECTING,
  LiveStreamState.PENDING,
];

interface StateOption {
  id: LiveStreamState | '';
  labelKey: string;
}

const STATE_OPTIONS: StateOption[] = [
  { id: '', labelKey: 'allStates' },
  { id: LiveStreamState.RUNNING, labelKey: 'streamStateRunning' },
  { id: LiveStreamState.PAUSED, labelKey: 'streamStatePaused' },
  { id: LiveStreamState.RECONNECTING, labelKey: 'streamStateReconnecting' },
  { id: LiveStreamState.ERROR, labelKey: 'streamStateError' },
  { id: LiveStreamState.STOPPED, labelKey: 'streamStateStopped' },
];

export interface LiveStreamModalProps {
  open: boolean;
  onClose: () => void;
}

/**
 * Live-stream management surface.
 *
 * Freshness comes from the Pipeline Manager's `streams:sync` broadcast. The
 * server only polls dataprep while this room has members, so the subscribe on
 * open / unsubscribe on close is what bounds the backend work - it is not a
 * cosmetic optimisation.
 *
 * The interval here is a fallback for when the socket is down; it checks
 * `socket.connected` on every tick instead of being installed conditionally,
 * because the connection can drop while the modal is already open.
 */
const LiveStreamModal: FC<LiveStreamModalProps> = ({ open, onClose }) => {
  const { t } = useTranslation();
  const dispatch = useAppDispatch();
  const { streams, status, error, filters } = useSelector(streamsSelector);

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<LiveStream | null>(null);
  const [deleting, setDeleting] = useState<LiveStream | null>(null);
  const [busyIds, setBusyIds] = useState<string[]>([]);
  const [tagInput, setTagInput] = useState('');

  const refresh = useCallback(() => {
    void dispatch(streamsLoad(filters));
  }, [dispatch, filters]);

  useEffect(() => {
    if (!open) return;

    socket.emit('streams:subscribe');
    refresh();

    const timer = window.setInterval(() => {
      if (!socket.connected) refresh();
    }, FALLBACK_POLL_MS);

    return () => {
      window.clearInterval(timer);
      socket.emit('streams:unsubscribe');
    };
  }, [open, refresh]);

  const visible = useMemo(() => {
    // The state filter is applied server-side; the tag box filters the
    // already-synced list so typing does not fire a request per keystroke.
    const needle = tagInput.trim().toLowerCase();
    if (!needle) return streams;
    return streams.filter(
      (stream) =>
        stream.tags?.some((tag) => tag.toLowerCase().includes(needle)) ||
        stream.stream_name.toLowerCase().includes(needle),
    );
  }, [streams, tagInput]);

  const withBusy = async (streamId: string, action: () => Promise<void>) => {
    setBusyIds((previous) => [...previous, streamId]);
    try {
      await action();
    } finally {
      setBusyIds((previous) => previous.filter((id) => id !== streamId));
    }
  };

  const handleToggleState = (stream: LiveStream) => {
    const next = PAUSABLE.includes(stream.state)
      ? LiveStreamState.PAUSED
      : LiveStreamState.RUNNING;

    void withBusy(stream.stream_id, async () => {
      try {
        await dispatch(
          streamUpdate({
            streamId: stream.stream_id,
            payload: { state: next },
          }),
        ).unwrap();
      } catch (thunkError) {
        notify(
          typeof thunkError === 'string' ? thunkError : t('streamUpdateFailed'),
          NotificationSeverity.ERROR,
          6000,
        );
      }
    });
  };

  const handleStateFilter = (state: LiveStreamState | '') => {
    dispatch(StreamsActions.setFilters({ ...filters, state }));
    void dispatch(streamsLoad({ ...filters, state }));
  };

  // Show the loader only when there is nothing to show yet. A refresh over an
  // already-populated list must not blank the rows out from under the user.
  const loading =
    status === StateActionStatus.IN_PROGRESS && streams.length === 0 && !error;
  const selectedState =
    STATE_OPTIONS.find((option) => option.id === (filters.state ?? '')) ??
    STATE_OPTIONS[0];

  // Two Carbon modals must never be visible at once. Each open `Modal` runs
  // its own focus trap: the list modal's `onBlur` calls `wrapFocus` with its
  // own body node, so focus moving into a child modal's input is dragged
  // straight back out and keystrokes never land. Separately, this modal is
  // `passiveModal` without `preventCloseOnClickOutside`, so Carbon treats any
  // click that is not inside *its* container - including every click in the
  // child modal - as a click-outside and fires `onRequestClose`.
  //
  // Hiding the list while a child is open sidesteps both. The websocket
  // subscription keys off the `open` prop, not this value, so live counters
  // keep updating underneath.
  const childOpen = formOpen || deleting !== null;

  return (
    <>
      <StyledModal
        open={open && !childOpen}
        passiveModal
        modalHeading={t('liveStreams')}
        onRequestClose={onClose}
        size='lg'
      >
        <Description>{t('liveStreamsDescription')}</Description>

        {error && (
          <InlineNotification
            kind='error'
            lowContrast
            title={t('streamUpdateFailed')}
            subtitle={error}
            onCloseButtonClick={() => dispatch(StreamsActions.clearError())}
          />
        )}

        <Toolbar>
          <FilterCell>
            <Dropdown
              id='stream-state-filter'
              titleText={t('filterByState')}
              label={t('allStates')}
              size='md'
              items={STATE_OPTIONS}
              itemToString={(item: StateOption | null) =>
                item ? t(item.labelKey) : ''
              }
              selectedItem={selectedState}
              onChange={({ selectedItem }: { selectedItem: StateOption }) =>
                handleStateFilter(selectedItem?.id ?? '')
              }
            />
          </FilterCell>
          <FilterCell>
            <Search
              id='stream-tag-filter'
              size='md'
              labelText={t('filterByTag')}
              placeholder={t('filterByTag')}
              value={tagInput}
              onChange={(event) => setTagInput(event.target.value)}
            />
          </FilterCell>
          <Spacer />
          <Button
            kind='ghost'
            size='md'
            renderIcon={Renew}
            onClick={refresh}
            disabled={status === StateActionStatus.IN_PROGRESS}
          >
            {t('refreshStreams')}
          </Button>
          <Button
            size='md'
            renderIcon={Add}
            data-testid='add-stream-button'
            onClick={() => {
              setEditing(null);
              setFormOpen(true);
            }}
          >
            {t('addStream')}
          </Button>
        </Toolbar>

        {loading ? (
          <Centered>
            <Loading withOverlay={false} description={t('loadingStreams')} />
          </Centered>
        ) : visible.length === 0 ? (
          <EmptyState>
            <EmptyTitle>
              {streams.length === 0
                ? t('noStreamsAvailable')
                : t('noStreamsMatchFilter')}
            </EmptyTitle>
            {streams.length === 0 && <Muted>{t('noStreamsDescription')}</Muted>}
          </EmptyState>
        ) : (
          <StreamList
            streams={visible}
            busyIds={busyIds}
            onEdit={(stream) => {
              setEditing(stream);
              setFormOpen(true);
            }}
            onDelete={setDeleting}
            onToggleState={handleToggleState}
          />
        )}
      </StyledModal>

      <StreamFormModal
        key={`form-${formOpen}-${editing?.stream_id ?? 'new'}`}
        open={formOpen}
        stream={editing}
        onClose={() => {
          setFormOpen(false);
          setEditing(null);
        }}
      />

      <DeleteStreamConfirm
        key={`delete-${deleting?.stream_id ?? 'none'}`}
        stream={deleting}
        onClose={() => setDeleting(null)}
      />
    </>
  );
};

export default LiveStreamModal;
