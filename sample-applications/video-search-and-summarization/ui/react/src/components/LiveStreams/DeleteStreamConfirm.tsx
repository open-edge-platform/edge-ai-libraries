// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Checkbox, Modal } from '@carbon/react';
import { FC, useState } from 'react';
import { useTranslation } from 'react-i18next';
import styled from 'styled-components';
import { LiveStream } from '../../redux/streams/streams';
import { streamDelete } from '../../redux/streams/streamsSlice';
import { useAppDispatch } from '../../redux/store';
import { NotificationSeverity, notify } from '../Notification/notify';

const StyledModal = styled(Modal)`
  z-index: 8100 !important;

  & .cds--modal-container {
    z-index: 8100 !important;
  }
`;

const StreamName = styled.p`
  font-weight: 600;
  margin-bottom: 0.5rem;
`;

const Warning = styled.p`
  font-size: 0.75rem;
  color: var(--cds-text-error, #da1e28);
  margin-top: 0.25rem;
  margin-left: 1.75rem;
`;

export interface DeleteStreamConfirmProps {
  stream: LiveStream | null;
  onClose: () => void;
}

/**
 * Destructive confirmation for removing a camera.
 *
 * The backend retains embeddings and recorded media unless both purge flags
 * are set, which is the safe default but is NOT what "delete" implies. The
 * body text says so explicitly rather than leaving it to be discovered, and
 * the purge opt-in is a separate checkbox.
 */
const DeleteStreamConfirm: FC<DeleteStreamConfirmProps> = ({
  stream,
  onClose,
}) => {
  const { t } = useTranslation();
  const dispatch = useAppDispatch();
  // Reset comes from the parent remounting this component via `key` when the
  // selected stream changes, not from an effect that writes state.
  const [purge, setPurge] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const handleDelete = async () => {
    if (!stream || submitting) return;

    setSubmitting(true);
    try {
      await dispatch(
        streamDelete({
          streamId: stream.stream_id,
          purge: { purge_embeddings: purge, purge_media: purge },
        }),
      ).unwrap();
      notify(t('streamDeleteSuccess'), NotificationSeverity.SUCCESS);
      onClose();
    } catch (error) {
      notify(
        typeof error === 'string' ? error : t('streamDeleteFailed'),
        NotificationSeverity.ERROR,
        6000,
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <StyledModal
      open={stream !== null}
      danger
      modalHeading={t('confirmDeleteStream')}
      primaryButtonText={t('deleteStream')}
      secondaryButtonText={t('cancel')}
      primaryButtonDisabled={submitting}
      onRequestClose={onClose}
      onRequestSubmit={() => void handleDelete()}
      onSecondarySubmit={onClose}
      size='sm'
    >
      <StreamName>{stream?.stream_name}</StreamName>
      <p>{t('confirmDeleteStreamBody')}</p>
      <div style={{ marginTop: '1rem' }}>
        <Checkbox
          id='purge-stream-data'
          data-testid='purge-stream-data'
          labelText={t('purgeStreamData')}
          checked={purge}
          onChange={(_event, { checked }) => setPurge(checked)}
        />
        {purge && <Warning>{t('purgeStreamDataWarning')}</Warning>}
      </div>
    </StyledModal>
  );
};

export default DeleteStreamConfirm;
