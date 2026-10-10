// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { IconButton, Tag } from '@carbon/react';
import { Edit, PauseOutlineFilled, PlayOutlineFilled, TrashCan } from '@carbon/icons-react';
import { FC } from 'react';
import { useTranslation } from 'react-i18next';
import styled from 'styled-components';
import { LiveStream, LiveStreamState } from '../../redux/streams/streams';
import StreamStateTag from './StreamStateTag';

const Row = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.75rem 0.5rem;
  border-bottom: 1px solid var(--cds-border-subtle, #e0e0e0);

  &:last-child {
    border-bottom: none;
  }
`;

const Main = styled.div`
  flex: 1;
  min-width: 0;
`;

const Name = styled.p`
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
`;

const Url = styled.p`
  font-size: 0.75rem;
  color: var(--cds-text-secondary, #525252);
  font-family: monospace;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
`;

const Stats = styled.p`
  font-size: 0.75rem;
  color: var(--cds-text-secondary, #525252);
  margin-top: 0.25rem;
`;

const ErrorText = styled.p`
  font-size: 0.75rem;
  color: var(--cds-text-error, #da1e28);
  margin-top: 0.25rem;
  overflow: hidden;
  text-overflow: ellipsis;
`;

const Right = styled.div`
  display: flex;
  align-items: center;
  gap: 0.25rem;
  flex-shrink: 0;
`;

const TagRow = styled.div`
  margin-top: 0.25rem;
`;

/** States from which pausing is meaningful. */
const PAUSABLE = [
  LiveStreamState.RUNNING,
  LiveStreamState.STARTING,
  LiveStreamState.RECONNECTING,
  LiveStreamState.PENDING,
];

const formatUptime = (seconds?: number | null): string => {
  if (!seconds || seconds <= 0) return '-';
  const total = Math.floor(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${total % 60}s`;
  return `${total}s`;
};

export interface StreamRowProps {
  stream: LiveStream;
  onEdit: (stream: LiveStream) => void;
  onDelete: (stream: LiveStream) => void;
  onToggleState: (stream: LiveStream) => void;
  busy?: boolean;
}

const StreamRow: FC<StreamRowProps> = ({ stream, onEdit, onDelete, onToggleState, busy = false }) => {
  const { t } = useTranslation();
  const canPause = PAUSABLE.includes(stream.state);
  const stats = stream.stats ?? {
    frames_processed: 0,
    embeddings_created: 0,
    reconnect_count: 0,
  };

  return (
    <Row data-testid={`stream-row-${stream.stream_id}`}>
      <Main>
        <Name title={stream.stream_name}>{stream.stream_name}</Name>
        <Url title={stream.stream_url}>{stream.stream_url}</Url>
        <Stats>
          {stats.frames_processed?.toLocaleString() ?? 0} {t('framesProcessed')}
          {' · '}
          {stats.embeddings_created?.toLocaleString() ?? 0} {t('embeddingsCreated')}
          {' · '}
          {t('uptime')} {formatUptime(stats.uptime_seconds)}
          {stats.reconnect_count > 0 && ` · ${stats.reconnect_count} ${t('reconnects')}`}
        </Stats>
        {stream.state === LiveStreamState.ERROR && stream.last_error && (
          <ErrorText title={stream.last_error}>{stream.last_error}</ErrorText>
        )}
        {stream.tags?.length > 0 && (
          <TagRow>
            {stream.tags.map((tag) => (
              <Tag key={tag} type='outline' size='sm'>
                {tag}
              </Tag>
            ))}
          </TagRow>
        )}
      </Main>

      {/*
        Inline icon buttons rather than an OverflowMenu. Carbon's OverflowMenu
        portals its options into `document.body` at `z-index: 6000`
        (`$z-indexes.floating`), which paints *below* this modal, so the menu
        opened but was never visible. Its trigger tooltip also widened the row
        and forced a horizontal scrollbar. IconButton tooltips render inline,
        inside the modal's stacking context, and `align='top-end'` keeps them
        off the right edge.
      */}
      <Right>
        <StreamStateTag state={stream.state} />
        <IconButton
          size='sm'
          kind='ghost'
          align='top-end'
          autoAlign
          label={canPause ? t('pauseStream') : t('resumeStream')}
          disabled={busy}
          data-testid={`stream-toggle-${stream.stream_id}`}
          onClick={() => onToggleState(stream)}
        >
          {canPause ? <PauseOutlineFilled /> : <PlayOutlineFilled />}
        </IconButton>
        <IconButton
          size='sm'
          kind='ghost'
          align='top-end'
          autoAlign
          label={t('editStream')}
          disabled={busy}
          data-testid={`stream-edit-${stream.stream_id}`}
          onClick={() => onEdit(stream)}
        >
          <Edit />
        </IconButton>
        <IconButton
          size='sm'
          kind='ghost'
          align='top-end'
          autoAlign
          label={t('deleteStream')}
          disabled={busy}
          data-testid={`stream-delete-${stream.stream_id}`}
          onClick={() => onDelete(stream)}
        >
          <TrashCan />
        </IconButton>
      </Right>
    </Row>
  );
};

export default StreamRow;
