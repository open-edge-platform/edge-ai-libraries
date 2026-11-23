// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { IntersectionMarker } from '../components/MapView/intersectionMarkers';
import MapView, { resolveTileUrl } from '../components/MapView/MapView';

// Return the key, plus `:count` when a count is interpolated, which is enough to assert on.
vi.mock('react-i18next', async () => ({
  ...(await vi.importActual('react-i18next')),
  useTranslation: () => ({
    t: (key: string, options?: unknown) =>
      options && typeof options === 'object' && 'count' in options
        ? `${key}:${(options as { count: number }).count}`
        : key,
  }),
}));

// Isolate MapView's own pan/zoom/culling logic from the card.
vi.mock('../components/MapView/IntersectionCard', () => ({
  default: ({
    marker,
    left,
    top,
    horizontalOffset,
    placement,
  }: {
    marker: IntersectionMarker;
    left: number;
    top: number;
    horizontalOffset: number;
    placement: string;
  }) => (
    <div
      data-testid={`card-${marker.id}`}
      data-left={left}
      data-top={top}
      data-horizontal-offset={horizontalOffset}
      data-placement={placement}
      data-count={marker.resultIndices.length}
    >
      {marker.label}
    </div>
  ),
}));

const makeMarker = (overrides: Partial<IntersectionMarker>): IntersectionMarker => ({
  id: 'intersection_1',
  label: 'Intersection',
  lat: 0,
  lon: 0,
  resultIndices: [0],
  cameras: [],
  ...overrides,
});

const stubContainerSize = (width: number, height: number) => {
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
    width,
    height,
    top: 0,
    left: 0,
    right: width,
    bottom: height,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  } as DOMRect);
};

describe('MapView', () => {
  beforeEach(() => {
    stubContainerSize(800, 600);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('shows the empty-state notice when there are no markers', () => {
    render(<MapView markers={[]} unmapped={[]} />);
    expect(screen.getByText('NoIntersectionLocations')).toBeInTheDocument();
  });

  it('renders one card per intersection once the viewport is measured', () => {
    const markers = [
      makeMarker({ id: 'intersection_1', label: 'Main' }),
      makeMarker({ id: 'intersection_2', label: 'Broadway' }),
    ];
    render(<MapView markers={markers} unmapped={[]} />);

    expect(screen.getByTestId('card-intersection_1')).toBeInTheDocument();
    expect(screen.getByTestId('card-intersection_2')).toBeInTheDocument();
  });

  it('refits when a different set of intersections is shown', () => {
    const { rerender } = render(
      <MapView markers={[makeMarker({ id: 'intersection_1', lat: 0, lon: 0 })]} unmapped={[]} />,
    );

    rerender(<MapView markers={[makeMarker({ id: 'intersection_2', lat: 40, lon: 100 })]} unmapped={[]} />);

    expect(Number(screen.getByTestId('card-intersection_2').getAttribute('data-left'))).toBeCloseTo(400, 3);
    expect(Number(screen.getByTestId('card-intersection_2').getAttribute('data-top'))).toBeCloseTo(300, 3);
  });

  it('keeps the user pan/zoom when results update at the same intersections', () => {
    const markers = [makeMarker({ id: 'west', lon: -20 }), makeMarker({ id: 'east', lon: 20 })];
    const { rerender } = render(<MapView markers={markers} unmapped={[]} />);

    fireEvent.click(screen.getByLabelText('ZoomOut'));
    const zoomedOutLeft = screen.getByTestId('card-west').getAttribute('data-left');

    // A watched-query refresh: same intersections, new result counts, new array identities.
    rerender(
      <MapView
        markers={[makeMarker({ id: 'west', lon: -20, resultIndices: [0, 1] }), makeMarker({ id: 'east', lon: 20 })]}
        unmapped={[]}
      />,
    );

    expect(screen.getByTestId('card-west').getAttribute('data-count')).toBe('2');
    expect(screen.getByTestId('card-west').getAttribute('data-left')).toBe(zoomedOutLeft);
  });

  it('refits when the map container becomes smaller so every marker stays visible', () => {
    const markers = [makeMarker({ id: 'west', lon: -20 }), makeMarker({ id: 'east', lon: 20 })];
    render(<MapView markers={markers} unmapped={[]} />);

    stubContainerSize(400, 300);
    fireEvent.resize(window);

    const west = Number(screen.getByTestId('card-west').getAttribute('data-left'));
    const east = Number(screen.getByTestId('card-east').getAttribute('data-left'));
    expect(west).toBeGreaterThanOrEqual(60);
    expect(east).toBeLessThanOrEqual(340);
  });

  it('restores the best-fit view after manual zooming', () => {
    const markers = [makeMarker({ id: 'west', lon: -20 }), makeMarker({ id: 'east', lon: 20 })];
    render(<MapView markers={markers} unmapped={[]} />);

    const initialWest = screen.getByTestId('card-west').getAttribute('data-left');
    fireEvent.click(screen.getByLabelText('ZoomOut'));
    expect(screen.getByTestId('card-west').getAttribute('data-left')).not.toBe(initialWest);

    fireEvent.click(screen.getByLabelText('FitIntersections'));
    expect(screen.getByTestId('card-west').getAttribute('data-left')).toBe(initialWest);
  });

  it('does not capture the pointer for presses on the zoom controls, so their click reaches the button', () => {
    render(<MapView markers={[makeMarker({})]} unmapped={[]} />);
    const mapContainer = screen.getByTestId('map-view');
    const setPointerCapture = vi.fn();
    mapContainer.setPointerCapture = setPointerCapture;

    fireEvent.pointerDown(screen.getByLabelText('ZoomIn'), { clientX: 10, clientY: 10 });
    expect(setPointerCapture).not.toHaveBeenCalled();

    fireEvent.pointerDown(mapContainer, { clientX: 400, clientY: 300 });
    expect(setPointerCapture).toHaveBeenCalledTimes(1);
  });

  it('culls a marker after panning it beyond the viewport margin', () => {
    render(<MapView markers={[makeMarker({ id: 'intersection_1' })]} unmapped={[]} />);

    const mapContainer = screen.getByTestId('map-view');
    fireEvent.pointerDown(mapContainer, { clientX: 400, clientY: 300 });
    fireEvent.pointerMove(mapContainer, { clientX: 1400, clientY: 300 });

    expect(screen.queryByTestId('card-intersection_1')).toBeNull();
  });

  it('renders OpenStreetMap tiles by default and the attribution', () => {
    render(<MapView markers={[makeMarker({})]} unmapped={[]} />);
    expect(document.querySelector('img')?.getAttribute('src')).toContain('https://tile.openstreetmap.org/');
    expect(screen.getByText('MapAttribution')).toBeInTheDocument();
  });

  it('lists unmapped tags only when some results cannot be placed', () => {
    const { rerender } = render(<MapView markers={[makeMarker({})]} unmapped={[]} />);
    expect(screen.queryByTestId('unmapped-notice')).toBeNull();

    rerender(
      <MapView
        markers={[makeMarker({})]}
        unmapped={[
          { tag: 'camera1', count: 2 },
          { tag: 'intersection_9-camera1', count: 1 },
        ]}
      />,
    );
    expect(screen.getByTestId('unmapped-notice')).toHaveTextContent('UnmappedTags:3');
  });

  it('reports the number of unmapped results when provided, not the sum of tag counts', () => {
    render(
      <MapView
        markers={[makeMarker({})]}
        unmapped={[
          { tag: 'lobby', count: 1 },
          { tag: 'night', count: 1 },
        ]}
        unmappedResults={1}
      />,
    );
    expect(screen.getByTestId('unmapped-notice')).toHaveTextContent('UnmappedTags:1');
  });

  it('refits when an existing intersection moves', () => {
    const { rerender } = render(<MapView markers={[makeMarker({ id: 'a', lat: 0, lon: 0 })]} unmapped={[]} />);

    rerender(<MapView markers={[makeMarker({ id: 'a', lat: 40, lon: 100 })]} unmapped={[]} />);

    expect(Number(screen.getByTestId('card-a').getAttribute('data-left'))).toBeCloseTo(400, 3);
    expect(Number(screen.getByTestId('card-a').getAttribute('data-top'))).toBeCloseTo(300, 3);
  });

  it('shows the stale-locations notice only when locations may be out of date', () => {
    const { rerender } = render(<MapView markers={[makeMarker({})]} unmapped={[]} />);
    expect(screen.queryByText('LocationsStale')).toBeNull();

    rerender(<MapView markers={[makeMarker({})]} unmapped={[]} stale />);
    expect(screen.getByRole('status')).toHaveTextContent('LocationsStale');
  });

  it('treats a small pointer movement as a click, not a pan (drag threshold)', () => {
    render(<MapView markers={[makeMarker({ id: 'intersection_1' })]} unmapped={[]} />);

    const mapContainer = screen.getByTestId('map-view');
    const before = screen.getByTestId('card-intersection_1').getAttribute('data-left');

    fireEvent.pointerDown(mapContainer, { clientX: 100, clientY: 100 });
    fireEvent.pointerMove(mapContainer, { clientX: 101, clientY: 101 });
    fireEvent.pointerUp(mapContainer, { clientX: 101, clientY: 101 });

    expect(screen.getByTestId('card-intersection_1').getAttribute('data-left')).toBe(before);
  });

  it('pans the view once the drag threshold is exceeded', () => {
    render(<MapView markers={[makeMarker({ id: 'intersection_1', lat: 10, lon: 10 })]} unmapped={[]} />);

    const mapContainer = screen.getByTestId('map-view');
    const before = screen.getByTestId('card-intersection_1').getAttribute('data-left');

    fireEvent.pointerDown(mapContainer, { clientX: 100, clientY: 100 });
    fireEvent.pointerMove(mapContainer, { clientX: 200, clientY: 100 });

    expect(screen.getByTestId('card-intersection_1').getAttribute('data-left')).not.toBe(before);
  });

  it('shifts a card inward when its anchor approaches the viewport edge', () => {
    render(<MapView markers={[makeMarker({ id: 'intersection_1' })]} unmapped={[]} />);

    const mapContainer = screen.getByTestId('map-view');
    fireEvent.pointerDown(mapContainer, { clientX: 400, clientY: 300 });
    fireEvent.pointerMove(mapContainer, { clientX: 20, clientY: 300 });

    expect(Number(screen.getByTestId('card-intersection_1').getAttribute('data-horizontal-offset'))).toBeGreaterThan(0);
  });

  it('zooms with the mouse wheel and prevents the page from scrolling', () => {
    const markers = [makeMarker({ id: 'west', lon: -20 }), makeMarker({ id: 'east', lon: 20 })];
    render(<MapView markers={markers} unmapped={[]} />);
    const before = screen.getByTestId('card-west').getAttribute('data-left');

    const notPrevented = fireEvent.wheel(screen.getByTestId('map-view'), { deltaY: -100, clientX: 400, clientY: 300 });

    expect(notPrevented).toBe(false);
    expect(screen.getByTestId('card-west').getAttribute('data-left')).not.toBe(before);
  });
});

describe('resolveTileUrl', () => {
  it('uses a configured tile template', () => {
    expect(resolveTileUrl('http://tiles.lab/{z}/{x}/{y}.png')).toBe('http://tiles.lab/{z}/{x}/{y}.png');
  });

  it('falls back to OpenStreetMap for an unset, placeholder or malformed value', () => {
    const osm = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
    expect(resolveTileUrl(undefined)).toBe(osm);
    expect(resolveTileUrl('')).toBe(osm);
    expect(resolveTileUrl('APP_' + 'MAP_TILE_URL')).toBe(osm);
    expect(resolveTileUrl('http://tiles.lab/no-template.png')).toBe(osm);
  });
});
