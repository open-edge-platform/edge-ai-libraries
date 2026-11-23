// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { IntersectionCard } from '../components/MapView/IntersectionCard';
import { IntersectionMarker } from '../components/MapView/intersectionMarkers';

vi.mock('react-i18next', async () => ({
  ...(await vi.importActual('react-i18next')),
  useTranslation: () => ({
    t: (key: string, options?: { count?: number }) => (options?.count !== undefined ? `${key}:${options.count}` : key),
  }),
}));

const makeMarker = (overrides: Partial<IntersectionMarker> = {}): IntersectionMarker => ({
  id: 'intersection_1',
  label: 'Main St',
  lat: 37.3875,
  lon: -121.9636,
  resultIndices: [0],
  cameras: [{ tag: 'intersection_1-camera1', label: 'intersection_1-camera1', resultIndices: [0] }],
  ...overrides,
});

const renderCard = (marker: IntersectionMarker, onActivate = vi.fn()) => ({
  onActivate,
  ...render(<IntersectionCard marker={marker} left={100} top={200} isActive={false} onActivate={onActivate} />),
});

describe('IntersectionCard', () => {
  it('shows only the intersection name and result count', () => {
    renderCard(
      makeMarker({
        label: 'Broadway & El Camino',
        resultIndices: [0, 1, 2],
        status: { level: 'high' },
      }),
    );
    const card = screen.getByTestId('intersection-card-intersection_1');

    expect(screen.getByText('Broadway & El Camino')).toBeInTheDocument();
    expect(screen.getByText('IntersectionClipCount:3')).toBeInTheDocument();
    expect(card.querySelector('video')).toBeNull();
    expect(card.querySelector('button')).toBeNull();
    expect(screen.queryByText(/^Lat:/)).toBeNull();
    expect(screen.queryByRole('img')).toBeNull();
  });

  it('activates the marker on hover so it is drawn on top', () => {
    const { onActivate } = renderCard(makeMarker());

    fireEvent.mouseEnter(screen.getByTestId('intersection-card-intersection_1'));

    expect(onActivate).toHaveBeenCalledWith('intersection_1');
  });

  it('lets pointer presses reach the map so the pin does not block panning', () => {
    const onMapPointerDown = vi.fn();
    render(
      <div onPointerDown={onMapPointerDown}>
        <IntersectionCard marker={makeMarker()} left={0} top={0} isActive={false} onActivate={vi.fn()} />
      </div>,
    );

    fireEvent.pointerDown(screen.getByText('Main St'));

    expect(onMapPointerDown).toHaveBeenCalled();
  });
});
