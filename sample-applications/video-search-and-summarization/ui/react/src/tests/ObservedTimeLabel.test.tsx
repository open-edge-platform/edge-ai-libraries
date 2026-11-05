// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import '../utils/i18n';
import { ObservedTimeLabel, formatOffset } from '../components/Search/ObservedTimeLabel';
import { SearchResult } from '../redux/search/search';

const upload = (observedAt: string, createdAt = '2026-10-21T02:55:02.772Z') =>
  ({
    id: 'r',
    type: 'Document',
    page_content: '',
    metadata: {} as any,
    timeSource: 'upload',
    observedAt,
    video: { createdAt } as any,
  }) as SearchResult;

describe('formatOffset', () => {
  it('renders m:ss below an hour and h:mm:ss from an hour', () => {
    expect(formatOffset(0)).toBe('0:00');
    expect(formatOffset(13.51)).toBe('0:13');
    expect(formatOffset(61.8)).toBe('1:01');
    expect(formatOffset(3725)).toBe('1:02:05');
  });
});

describe('ObservedTimeLabel', () => {
  it('shows the offset of the match after the upload time', () => {
    render(<ObservedTimeLabel result={upload('2026-10-21T02:55:16.285Z')} />);
    const time = new Date('2026-10-21T02:55:02.772Z').toLocaleString();
    expect(screen.getByTestId('observed-time')).toHaveTextContent(`Uploaded ${time} · at 0:13`);
  });

  it('distinguishes hits from the same upload by their offset', () => {
    render(
      <>
        <ObservedTimeLabel result={upload('2026-10-21T02:55:10.029Z')} />
        <ObservedTimeLabel result={upload('2026-10-21T02:56:04.583Z')} />
      </>,
    );
    const labels = screen.getAllByTestId('observed-time').map((el) => el.textContent);
    expect(labels[0]).toMatch(/· at 0:07$/);
    expect(labels[1]).toMatch(/· at 1:01$/);
  });

  it('falls back to the upload time alone when the offset is unknown', () => {
    render(<ObservedTimeLabel result={upload('2026-10-21T02:55:00.000Z')} />);
    expect(screen.getByTestId('observed-time').textContent).not.toContain('· at');
  });

  it('shows capture time for live hits', () => {
    const live = { ...upload('2026-10-21T02:55:16.285Z'), timeSource: 'live', video: undefined } as any;
    render(<ObservedTimeLabel result={live} />);
    expect(screen.getByTestId('observed-time')).toHaveTextContent(
      `Captured ${new Date('2026-10-21T02:55:16.285Z').toLocaleString()}`,
    );
  });
});
