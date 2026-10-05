// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import {
  Checkbox,
  Modal,
  NumberInput,
  TextArea,
  TextInput,
  Toggletip,
  ToggletipButton,
  ToggletipContent,
} from '@carbon/react';
import { Information } from '@carbon/icons-react';
import { FC, ReactElement, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import styled from 'styled-components';
import { useAppDispatch } from '../../redux/store';
import { LiveStream, LiveStreamCreatePayload, LiveStreamUpdatePayload } from '../../redux/streams/streams';
import { streamErrorMessage, streamsApi } from '../../redux/streams/streamsApi';
import { StreamsActions, streamUpdate } from '../../redux/streams/streamsSlice';
import { NotificationSeverity, notify } from '../Notification/notify';

const StyledModal = styled(Modal)`
  z-index: 8100 !important;

  & .cds--modal-container {
    z-index: 8100 !important;
  }
`;

const Field = styled.div`
  margin-bottom: 1rem;
`;

const ReadOnlyValue = styled.p`
  font-family: monospace;
  word-break: break-all;
  background: var(--cds-layer, #f4f4f4);
  padding: 0.5rem;
  margin: 0.25rem 0;
`;

const HelpText = styled.p`
  font-size: 0.75rem;
  color: var(--cds-text-secondary, #525252);
`;

const LabelRow = styled.span`
  display: flex;
  align-items: center;
  gap: 0.25rem;
`;

const RequiredMark = styled.span`
  color: var(--cds-support-error, #da1e28);
`;

const OptionalMark = styled.span`
  color: var(--cds-text-secondary, #525252);
  font-weight: 400;
`;

const RTSP_URL = /^rtsps?:\/\/\S+$/i;

/**
 * Form defaults, mirroring the ingestion service's own defaults
 * (`FRAME_INTERVAL`, `ENABLE_OBJECT_DETECTION`, `DETECTION_CONFIDENCE` in
 * multimodal-dataprep settings). The form always sends these fields, so a
 * value that disagrees with the service silently overrides it - keep them in
 * step. A deployment that overrides the service defaults via environment
 * variables is not reflected here.
 */
const DEFAULT_FRAME_INTERVAL = 15;
const DEFAULT_ENABLE_DETECTION = true;
const DEFAULT_DETECTION_CONFIDENCE = 0.85;

export interface StreamFormModalProps {
  open: boolean;
  onClose: () => void;
  /** Supplied in edit mode; absent in create mode. */
  stream?: LiveStream | null;
}

interface FormState {
  streamUrl: string;
  streamName: string;
  description: string;
  tags: string;
  sensorId: string;
  frameInterval: number;
  enableDetection: boolean;
  detectionConfidence: number;
  startImmediately: boolean;
}

const emptyForm: FormState = {
  streamUrl: '',
  streamName: '',
  description: '',
  tags: '',
  sensorId: '',
  frameInterval: DEFAULT_FRAME_INTERVAL,
  enableDetection: DEFAULT_ENABLE_DETECTION,
  detectionConfidence: DEFAULT_DETECTION_CONFIDENCE,
  startImmediately: true,
};

const formStateFor = (stream: LiveStream | null): FormState =>
  stream
    ? {
        streamUrl: stream.stream_url,
        streamName: stream.stream_name ?? '',
        description: stream.description ?? '',
        tags: (stream.tags ?? []).join(', '),
        sensorId: stream.sensor_id ?? '',
        frameInterval: stream.frame_interval ?? DEFAULT_FRAME_INTERVAL,
        enableDetection: stream.enable_object_detection ?? DEFAULT_ENABLE_DETECTION,
        detectionConfidence: stream.detection_confidence ?? DEFAULT_DETECTION_CONFIDENCE,
        startImmediately: true,
      }
    : emptyForm;

const parseTags = (raw: string): string[] =>
  raw
    .split(',')
    .map((tag) => tag.trim())
    .filter((tag) => tag.length > 0);

/**
 * Add / edit form for a live RTSP stream.
 *
 * Two deliberate choices:
 *
 * 1. In edit mode the RTSP URL is read-only text, not an input. The backend's
 *    update API has no `stream_url` field, so an editable control could never
 *    apply the change - and the value shown is redacted, so echoing it back
 *    would be meaningless anyway.
 * 2. Creation calls `streamsApi` directly rather than dispatching a thunk.
 *    The create payload holds the credentialed URL, and a thunk would record
 *    it on the action's `meta.arg` where any action log would capture it.
 */
const StreamFormModal: FC<StreamFormModalProps> = ({ open, onClose, stream = null }) => {
  const { t } = useTranslation();
  const dispatch = useAppDispatch();

  const isEdit = stream !== null;
  // Initialised once per mount. The parent remounts this component via `key`
  // whenever the modal opens or the edited stream changes, which resets the
  // form without an effect that writes state during render.
  const [form, setForm] = useState<FormState>(() => formStateFor(stream));
  const [submitting, setSubmitting] = useState(false);
  const [touched, setTouched] = useState(false);

  /**
   * Field label with an optional required/optional marker and an info
   * toggletip.
   *
   * Only `stream_url` is required by the ingestion API, so free-text fields
   * that may be left blank are explicitly marked optional. Checkboxes take no
   * marker: they always carry a value (checked or not), so calling them
   * optional would say nothing.
   */
  const fieldLabel = (
    label: string,
    info: string,
    marker: 'required' | 'optional' | 'none' = 'optional',
  ): ReactElement => (
    <LabelRow>
      {label}
      {marker === 'required' && <RequiredMark aria-label={t('requiredField')}>*</RequiredMark>}
      {marker === 'optional' && <OptionalMark>{t('optionalField')}</OptionalMark>}
      <Toggletip autoAlign>
        <ToggletipButton label={t('info')}>
          <Information />
        </ToggletipButton>
        <ToggletipContent>{info}</ToggletipContent>
      </Toggletip>
    </LabelRow>
  );

  const urlInvalid = useMemo(
    () => !isEdit && touched && !RTSP_URL.test(form.streamUrl.trim()),
    [form.streamUrl, isEdit, touched],
  );
  // `stream_url` is the only field the ingestion API requires; everything else
  // has a server-side default (the name falls back to the redacted URL).
  const canSubmit = isEdit || RTSP_URL.test(form.streamUrl.trim());

  const update = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((previous) => ({ ...previous, [key]: value }));

  const handleSubmit = async () => {
    setTouched(true);
    if (!canSubmit || submitting) return;

    setSubmitting(true);
    try {
      if (isEdit && stream) {
        const payload: LiveStreamUpdatePayload = {
          stream_name: form.streamName.trim() || undefined,
          description: form.description.trim(),
          tags: parseTags(form.tags),
          frame_interval: form.frameInterval,
          enable_object_detection: form.enableDetection,
          detection_confidence: form.detectionConfidence,
        };
        await dispatch(streamUpdate({ streamId: stream.stream_id, payload })).unwrap();
        notify(t('streamUpdateSuccess'), NotificationSeverity.SUCCESS);
      } else {
        const payload: LiveStreamCreatePayload = {
          stream_url: form.streamUrl.trim(),
          start: form.startImmediately,
          frame_interval: form.frameInterval,
          enable_object_detection: form.enableDetection,
          detection_confidence: form.detectionConfidence,
          tags: parseTags(form.tags),
        };
        if (form.streamName.trim()) payload.stream_name = form.streamName.trim();
        if (form.description.trim()) payload.description = form.description.trim();
        if (form.sensorId.trim()) payload.sensor_id = form.sensorId.trim();

        // Only the redacted response reaches Redux.
        const created = await streamsApi.createStream(payload);
        dispatch(StreamsActions.streamUpserted(created));
        notify(t('streamCreateSuccess'), NotificationSeverity.SUCCESS);
      }
      onClose();
    } catch (error) {
      notify(
        streamErrorMessage(error, isEdit ? t('streamUpdateFailed') : t('streamCreateFailed')),
        NotificationSeverity.ERROR,
        6000,
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <StyledModal
      open={open}
      modalHeading={isEdit ? t('editStream') : t('addStream')}
      primaryButtonText={isEdit ? t('editStream') : t('addStream')}
      secondaryButtonText={t('cancel')}
      primaryButtonDisabled={submitting}
      onRequestClose={onClose}
      onRequestSubmit={() => void handleSubmit()}
      onSecondarySubmit={onClose}
      size='sm'
    >
      <Field>
        {isEdit ? (
          <>
            <span className='cds--label'>{fieldLabel(t('streamUrl'), t('streamUrlInfo'), 'required')}</span>
            <ReadOnlyValue data-testid='stream-url-readonly'>{form.streamUrl}</ReadOnlyValue>
            <HelpText>{t('streamUrlImmutable')}</HelpText>
          </>
        ) : (
          <TextInput
            id='stream-url'
            data-testid='stream-url-input'
            labelText={fieldLabel(t('streamUrl'), t('streamUrlInfo'), 'required')}
            placeholder={t('streamUrlPlaceholder')}
            helperText={t('streamUrlHelp')}
            value={form.streamUrl}
            invalid={urlInvalid}
            invalidText={t('streamUrlInvalid')}
            onChange={(event) => update('streamUrl', event.target.value)}
            onBlur={() => setTouched(true)}
          />
        )}
      </Field>

      <Field>
        <TextInput
          id='stream-name'
          data-testid='stream-name-input'
          labelText={fieldLabel(t('streamName'), t('streamNameInfo'))}
          placeholder={t('streamNamePlaceholder')}
          value={form.streamName}
          onChange={(event) => update('streamName', event.target.value)}
        />
      </Field>

      <Field>
        <TextArea
          id='stream-description'
          labelText={fieldLabel(t('streamDescription'), t('streamDescriptionInfo'))}
          rows={2}
          value={form.description}
          onChange={(event) => update('description', event.target.value)}
        />
      </Field>

      <Field>
        <TextInput
          id='stream-tags'
          labelText={fieldLabel(t('streamTags'), t('streamTagsInfo'))}
          value={form.tags}
          onChange={(event) => update('tags', event.target.value)}
        />
      </Field>

      {!isEdit && (
        <Field>
          <TextInput
            id='stream-sensor-id'
            labelText={fieldLabel(t('streamSensorId'), t('streamSensorIdInfo'))}
            helperText={t('streamSensorIdHelp')}
            value={form.sensorId}
            onChange={(event) => update('sensorId', event.target.value)}
          />
        </Field>
      )}

      <Field>
        <NumberInput
          id='stream-frame-interval'
          label={fieldLabel(t('frameInterval'), t('frameIntervalInfo'), 'none')}
          helperText={t('frameIntervalHelp')}
          min={1}
          max={60}
          step={1}
          value={form.frameInterval}
          onChange={(_event, { value }) => update('frameInterval', Number(value) || DEFAULT_FRAME_INTERVAL)}
        />
      </Field>

      <Field>
        <Checkbox
          id='stream-enable-detection'
          labelText={fieldLabel(t('enableDetection'), t('enableDetectionInfo'), 'none')}
          checked={form.enableDetection}
          onChange={(_event, { checked }) => update('enableDetection', checked)}
        />
      </Field>

      {form.enableDetection && (
        <Field>
          <NumberInput
            id='stream-detection-confidence'
            label={fieldLabel(t('detectionConfidence'), t('detectionConfidenceInfo'), 'none')}
            min={0.1}
            max={1}
            step={0.05}
            value={form.detectionConfidence}
            onChange={(_event, { value }) =>
              update('detectionConfidence', Number(value) || DEFAULT_DETECTION_CONFIDENCE)
            }
          />
        </Field>
      )}

      {!isEdit && (
        <Field>
          <Checkbox
            id='stream-start-immediately'
            labelText={fieldLabel(t('startImmediately'), t('startImmediatelyInfo'), 'none')}
            checked={form.startImmediately}
            onChange={(_event, { checked }) => update('startImmediately', checked)}
          />
        </Field>
      )}
    </StyledModal>
  );
};

export default StreamFormModal;
