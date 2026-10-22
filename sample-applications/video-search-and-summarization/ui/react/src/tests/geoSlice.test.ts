// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { configureStore } from '@reduxjs/toolkit';
import axios from 'axios';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  buildTagIndex,
  IntersectionInfo,
  isValidLatLon,
  parseGeoResponse,
  resolveIntersection,
} from '../redux/geo/geo';
import { GeoActions, GeoReducer, geoSelector, initialState, LoadIntersections } from '../redux/geo/geoSlice';
import { RootState } from '../redux/store';

vi.mock('axios');
const mockedAxios = vi.mocked(axios);

const createStore = () => configureStore({ reducer: { geo: GeoReducer } });
const select = (store: ReturnType<typeof createStore>) =>
  geoSelector({ geo: store.getState().geo } as unknown as RootState);

const intersections: Record<string, IntersectionInfo> = {
  intersection_1: {
    label: 'Main St',
    lat: 37.5,
    lon: -122.2,
    cameras: { 'intersection_1-camera1': { direction: 'south' } },
  },
  intersection_2: { label: 'Broadway', lat: 37.6, lon: -122.3, cameras: {} },
  intersection_3: { label: 'Custom', lat: 37.7, lon: -122.4, cameras: { 'north-cam': { label: 'North approach' } } },
};

describe('geo helpers', () => {
  it('rejects latitudes outside the Web Mercator domain', () => {
    expect(isValidLatLon(85.0511287798066, 0)).toBe(true);
    expect(isValidLatLon(86, 0)).toBe(false);
    expect(isValidLatLon(0, 181)).toBe(false);
    expect(isValidLatLon('1', 0)).toBe(false);
  });

  it('parses a backend response and drops invalid intersections', () => {
    const parsed = parseGeoResponse({
      source: 'geo-api',
      stale: true,
      intersections: {
        intersection_1: {
          label: 'Main St',
          lat: 37.5,
          lon: -122.2,
          cameras: { 'intersection_1-camera1': { direction: 'south' } },
        },
        bad: { lat: 999, lon: 0 },
        noLabel: { lat: 1, lon: 2 },
      },
    });

    expect(parsed.source).toBe('geo-api');
    expect(parsed.stale).toBe(true);
    expect(Object.keys(parsed.intersections)).toEqual(['intersection_1', 'noLabel']);
    expect(parsed.intersections.noLabel.label).toBe('noLabel');
    expect(parsed.intersections.intersection_1.cameras['intersection_1-camera1']).toEqual({
      label: undefined,
      direction: 'south',
    });
  });

  it('treats an HTML or unexpected body as empty instead of throwing', () => {
    expect(parseGeoResponse('<!doctype html>')).toEqual({ intersections: {}, source: 'none', stale: false });
    expect(parseGeoResponse({ source: 'weird' }).source).toBe('none');
  });

  describe('resolveIntersection', () => {
    const tagIndex = buildTagIndex(intersections);

    it('maps a camera tag to its intersection by prefix', () => {
      expect(resolveIntersection('intersection_2-camera3', intersections, tagIndex)).toBe('intersection_2');
    });

    it('matches the -camera suffix case-insensitively', () => {
      expect(resolveIntersection('intersection_2-Camera3', intersections, tagIndex)).toBe('intersection_2');
    });

    it('prefers a camera explicitly listed under an intersection', () => {
      expect(resolveIntersection('north-cam', intersections, tagIndex)).toBe('intersection_3');
      expect(resolveIntersection('intersection_1-camera1', intersections, tagIndex)).toBe('intersection_1');
    });

    it('accepts a tag that is itself an intersection id', () => {
      expect(resolveIntersection('intersection_1', intersections, tagIndex)).toBe('intersection_1');
    });

    it('returns null for un-prefixed or unknown tags', () => {
      expect(resolveIntersection('camera1', intersections, tagIndex)).toBeNull();
      expect(resolveIntersection('intersection_9-camera1', intersections, tagIndex)).toBeNull();
      expect(resolveIntersection('lobby', intersections, tagIndex)).toBeNull();
    });
  });
});

describe('geoSlice', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('starts unloaded with no intersections', () => {
    expect(initialState).toEqual({
      intersections: {},
      source: 'none',
      stale: false,
      loaded: false,
      mapDrawerOpen: false,
    });
  });

  it('opens, closes and toggles the map drawer', () => {
    let state = GeoReducer(initialState, GeoActions.openMapDrawer());
    expect(state.mapDrawerOpen).toBe(true);
    state = GeoReducer(state, GeoActions.closeMapDrawer());
    expect(state.mapDrawerOpen).toBe(false);
    state = GeoReducer(state, GeoActions.toggleMapDrawer());
    expect(state.mapDrawerOpen).toBe(true);
  });

  it('loads intersections from the pipeline-manager geo endpoint', async () => {
    mockedAxios.get.mockResolvedValueOnce({
      data: { source: 'geo-api', stale: false, fetchedAt: 'x', intersections },
    });

    const store = createStore();
    await store.dispatch(LoadIntersections());

    expect(mockedAxios.get).toHaveBeenCalledWith(expect.stringMatching(/\/geo\/intersections$/));
    const state = select(store);
    expect(state.loaded).toBe(true);
    expect(state.source).toBe('geo-api');
    expect(state.hasIntersections).toBe(true);
    expect(state.tagIndex.get('north-cam')).toBe('intersection_3');
  });

  it('keeps the last intersections and marks them stale when a refresh fails', async () => {
    mockedAxios.get.mockResolvedValueOnce({ data: { source: 'geo-api', stale: false, intersections } });
    mockedAxios.get.mockRejectedValueOnce(new Error('503'));

    const store = createStore();
    await store.dispatch(LoadIntersections());
    await store.dispatch(LoadIntersections());

    const state = select(store);
    expect(Object.keys(state.intersections)).toEqual(['intersection_1', 'intersection_2', 'intersection_3']);
    expect(state.stale).toBe(true);
  });

  it('reports no intersections when the first load fails', async () => {
    mockedAxios.get.mockRejectedValueOnce(new Error('network'));

    const store = createStore();
    await store.dispatch(LoadIntersections());

    const state = select(store);
    expect(state.loaded).toBe(true);
    expect(state.hasIntersections).toBe(false);
    expect(state.stale).toBe(false);
  });
});
