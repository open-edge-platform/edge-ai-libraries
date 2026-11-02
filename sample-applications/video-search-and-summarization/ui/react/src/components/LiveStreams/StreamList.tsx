// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { FC } from 'react';
import styled from 'styled-components';
import { LiveStream } from '../../redux/streams/streams';
import StreamRow from './StreamRow';

const List = styled.div`
  max-height: 24rem;
  overflow-y: auto;
  border: 1px solid var(--cds-border-subtle, #e0e0e0);
`;

export interface StreamListProps {
  streams: LiveStream[];
  onEdit: (stream: LiveStream) => void;
  onDelete: (stream: LiveStream) => void;
  onToggleState: (stream: LiveStream) => void;
  busyIds?: string[];
}

/**
 * Plain div list rather than a Carbon `DataTable`.
 *
 * Nothing else in this UI uses `DataTable`, and the row content here is not
 * tabular - it is a title block with secondary stats and an inline error.
 */
const StreamList: FC<StreamListProps> = ({
  streams,
  onEdit,
  onDelete,
  onToggleState,
  busyIds = [],
}) => (
  <List data-testid='stream-list'>
    {streams.map((stream) => (
      <StreamRow
        key={stream.stream_id}
        stream={stream}
        onEdit={onEdit}
        onDelete={onDelete}
        onToggleState={onToggleState}
        busy={busyIds.includes(stream.stream_id)}
      />
    ))}
  </List>
);

export default StreamList;
