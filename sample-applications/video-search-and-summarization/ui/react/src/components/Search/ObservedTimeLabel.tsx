// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { FC } from 'react';
import { useTranslation } from 'react-i18next';
import styled from 'styled-components';
import { SearchResult } from '../../redux/search/search';

const Label = styled.span`
  color: var(--color-gray-7, #525252);
  font-size: 0.75rem;
  font-variant-numeric: tabular-nums;
`;

const formatLocal = (iso?: string | null): string | null => {
  if (!iso) return null;
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? null : date.toLocaleString();
};

/** Seconds as m:ss, or h:mm:ss from an hour. */
export const formatOffset = (seconds: number): string => {
  const total = Math.max(0, Math.floor(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const ss = String(total % 60).padStart(2, '0');
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${ss}` : `${m}:${ss}`;
};

/** Offset of the match into its video: observedAt minus the upload time. */
const uploadOffset = (result: SearchResult): number | null => {
  const uploaded = Date.parse(result.video?.createdAt ?? '');
  const observed = Date.parse(result.observedAt ?? '');
  if (Number.isNaN(uploaded) || Number.isNaN(observed) || observed < uploaded) return null;
  return (observed - uploaded) / 1000;
};

/**
 * When a hit happened: capture time for live hits, upload time for uploaded
 * videos, followed by the match's offset into the video, which orders hits
 * from the same video on the timeline.
 */
export const ObservedTimeLabel: FC<{ result?: SearchResult }> = ({ result }) => {
  const { t } = useTranslation();
  if (!result?.observedAt) return null;

  if (result.timeSource === 'live') {
    const time = formatLocal(result.observedAt);
    return time ? (
      <Label data-testid='observed-time' title={result.observedAt}>
        {t('observedLive', 'Captured {{time}}', { time })}
      </Label>
    ) : null;
  }

  const uploaded = result.video?.createdAt ?? result.observedAt;
  const time = formatLocal(uploaded);
  if (!time) return null;
  const offset = uploadOffset(result);
  return (
    <Label
      data-testid='observed-time'
      title={t(
        'observedUploadHint',
        'Uploaded videos are placed on the timeline by upload time plus the offset of the match.',
      )}
    >
      {offset === null
        ? t('observedUpload', 'Uploaded {{time}}', { time })
        : t('observedUploadAt', 'Uploaded {{time}} · at {{offset}}', { time, offset: formatOffset(offset) })}
    </Label>
  );
};

export default ObservedTimeLabel;
