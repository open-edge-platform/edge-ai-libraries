// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { normalizeIntersections } from './geo.model';

describe('normalizeIntersections', () => {
  let warn: jest.Mock;

  beforeEach(() => {
    warn = jest.fn();
  });

  it('returns an empty map for non-object input', () => {
    expect(normalizeIntersections(null, warn)).toEqual({});
    expect(normalizeIntersections('<html></html>', warn)).toEqual({});
    expect(normalizeIntersections([1, 2], warn)).toEqual({});
    expect(normalizeIntersections({}, warn)).toEqual({});
  });

  it('parses the intersections contract and defaults the label to the id', () => {
    const result = normalizeIntersections(
      {
        version: 1,
        intersections: {
          intersection_1: {
            label: 'Main St & 5th Ave',
            lat: 37.51358,
            lon: -122.25591,
            source: 'ws://internal:8081',
            cameras: {
              'intersection_1-camera1': { direction: 'south' },
              'intersection_1-camera3': {
                label: 'North approach',
                direction: 'north',
              },
            },
            status: { level: 'HIGH', density: 14 },
          },
          intersection_2: { lat: 37.5391, lon: -122.30871 },
        },
      },
      warn,
    );

    expect(result).toEqual({
      intersection_1: {
        label: 'Main St & 5th Ave',
        lat: 37.51358,
        lon: -122.25591,
        cameras: {
          'intersection_1-camera1': { label: undefined, direction: 'south' },
          'intersection_1-camera3': {
            label: 'North approach',
            direction: 'north',
          },
        },
        status: {
          level: 'HIGH',
          density: 14,
          incident: undefined,
          updated_at: undefined,
        },
      },
      intersection_2: {
        label: 'intersection_2',
        lat: 37.5391,
        lon: -122.30871,
        cameras: {},
        status: undefined,
      },
    });
    expect(warn).not.toHaveBeenCalled();
  });

  it('does not pass through unknown fields such as an internal source host', () => {
    const result = normalizeIntersections(
      {
        intersections: { intersection_1: { lat: 1, lon: 2, source: 'ws://x' } },
      },
      warn,
    );
    expect(result.intersection_1).not.toHaveProperty('source');
  });

  it('ignores a body without an intersections object', () => {
    const result = normalizeIntersections(
      {
        cameras: { camera1: { lat: 37.3875, lon: -121.9636, label: 'Lobby' } },
      },
      warn,
    );
    expect(result).toEqual({});
  });

  it.each([
    ['latitude out of range', { lat: 91, lon: 0 }],
    ['longitude out of range', { lat: 0, lon: 200 }],
    ['latitude as string', { lat: '37', lon: 0 }],
    ['NaN', { lat: NaN, lon: 0 }],
    ['missing latitude', { lon: 0 }],
    ['non-object body', 5],
  ])('drops an intersection with %s', (_name, body) => {
    const result = normalizeIntersections(
      { intersections: { bad: body, good: { lat: 1, lon: 1 } } },
      warn,
    );
    expect(Object.keys(result)).toEqual(['good']);
    expect(warn).toHaveBeenCalledTimes(1);
  });

  it('drops ids that contain unsafe characters', () => {
    const result = normalizeIntersections(
      {
        intersections: {
          'si 1': { lat: 1, lon: 1 },
          'a/b': { lat: 1, lon: 1 },
        },
      },
      warn,
    );
    expect(result).toEqual({});
    expect(warn).toHaveBeenCalledTimes(2);
  });
});
