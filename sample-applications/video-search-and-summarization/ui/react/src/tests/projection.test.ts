// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import {
  fitBounds,
  lonLatToScreen,
  lonLatToWorld,
  MAX_ZOOM,
  MIN_ZOOM,
  screenToLonLat,
  visibleTiles,
  worldSize,
  worldToLonLat,
} from '../components/MapView/projection';

describe('projection', () => {
  describe('worldSize', () => {
    it('doubles the world pixel size for every zoom level', () => {
      expect(worldSize(0)).toBe(256);
      expect(worldSize(1)).toBe(512);
      expect(worldSize(4)).toBe(256 * 16);
    });
  });

  describe('lonLatToWorld', () => {
    it('places (0, 0) at the center of the world at zoom 0', () => {
      const { x, y } = lonLatToWorld(0, 0, 0);
      expect(x).toBeCloseTo(128, 5);
      expect(y).toBeCloseTo(128, 5);
    });

    it('places the west edge of the map at x=0 and the east edge at the world size', () => {
      const west = lonLatToWorld(-180, 0, 2);
      const east = lonLatToWorld(180, 0, 2);
      expect(west.x).toBeCloseTo(0, 5);
      expect(east.x).toBeCloseTo(worldSize(2), 5);
    });

    it('clamps extreme latitudes instead of producing Infinity/NaN', () => {
      const northPole = lonLatToWorld(0, 90, 5);
      const southPole = lonLatToWorld(0, -90, 5);
      expect(Number.isFinite(northPole.y)).toBe(true);
      expect(Number.isFinite(southPole.y)).toBe(true);
    });
  });

  describe('lonLatToWorld / worldToLonLat round-trip', () => {
    const fixtures: Array<{ lon: number; lat: number; zoom: number }> = [
      { lon: 0, lat: 0, zoom: 0 },
      { lon: -121.9636, lat: 37.3875, zoom: 10 },
      { lon: 139.6917, lat: 35.6895, zoom: 15 },
      { lon: -179.9, lat: -60, zoom: 3 },
      { lon: 12.4964, lat: 41.9028, zoom: 18 },
    ];

    it.each(fixtures)('round-trips lon=$lon lat=$lat at zoom=$zoom', ({ lon, lat, zoom }) => {
      const world = lonLatToWorld(lon, lat, zoom);
      const back = worldToLonLat(world.x, world.y, zoom);

      expect(back.lon).toBeCloseTo(lon, 6);
      expect(back.lat).toBeCloseTo(lat, 6);
    });
  });

  describe('lonLatToScreen / screenToLonLat', () => {
    it('projects the view center to the middle of the viewport', () => {
      const view = { center: { lon: -121.9636, lat: 37.3875 }, zoom: 12, width: 800, height: 600 };
      const screen = lonLatToScreen(view.center.lon, view.center.lat, view);

      expect(screen.x).toBeCloseTo(400, 5);
      expect(screen.y).toBeCloseTo(300, 5);
    });

    it('round-trips through screenToLonLat', () => {
      const view = { center: { lon: 10, lat: 45 }, zoom: 8, width: 1024, height: 768 };
      const screen = lonLatToScreen(10.5, 45.5, view);
      const back = screenToLonLat(screen.x, screen.y, view);

      expect(back.lon).toBeCloseTo(10.5, 5);
      expect(back.lat).toBeCloseTo(45.5, 5);
    });
  });

  describe('visibleTiles', () => {
    it('scales source tiles to the same fractional zoom used by markers', () => {
      const view = { center: { lon: 0, lat: 0 }, zoom: 1.5, width: 800, height: 600 };
      const tiles = visibleTiles(view);
      const expectedTileSize = 256 * Math.SQRT2;

      expect(tiles.length).toBeGreaterThan(0);
      tiles.forEach((tile) => {
        expect(tile.z).toBe(1);
        expect(tile.size).toBeCloseTo(expectedTileSize, 5);
      });

      const sameRow = tiles.filter((tile) => tile.y === tiles[0].y).sort((a, b) => a.column - b.column);
      expect(sameRow[1].left - sameRow[0].left).toBeCloseTo(expectedTileSize, 5);
    });

    it('retains the unwrapped tile column so wrapped copies have unique identities', () => {
      const tiles = visibleTiles({ center: { lon: 0, lat: 0 }, zoom: 0, width: 800, height: 300 });

      expect(new Set(tiles.map((tile) => `${tile.z}-${tile.column}-${tile.y}`)).size).toBe(tiles.length);
      expect(new Set(tiles.map((tile) => `${tile.z}-${tile.x}-${tile.y}`)).size).toBeLessThan(tiles.length);
    });

    it('covers the whole world with 4 tiles at zoom 1', () => {
      const view = { center: { lon: 0, lat: 0 }, zoom: 1, width: 512, height: 512 };
      const tiles = visibleTiles(view);

      expect(tiles.length).toBeGreaterThanOrEqual(4);
      tiles.forEach((tile) => {
        expect(tile.z).toBe(1);
        expect(tile.x).toBeGreaterThanOrEqual(0);
        expect(tile.x).toBeLessThan(2);
        expect(tile.y).toBeGreaterThanOrEqual(0);
        expect(tile.y).toBeLessThan(2);
      });
    });

    it('wraps tile columns around the antimeridian', () => {
      const view = { center: { lon: 179.9, lat: 0 }, zoom: 4, width: 400, height: 400 };
      const tiles = visibleTiles(view);
      const tileCount = 2 ** 4;

      tiles.forEach((tile) => {
        expect(tile.x).toBeGreaterThanOrEqual(0);
        expect(tile.x).toBeLessThan(tileCount);
      });
    });

    it('drops tile rows outside the valid latitude range', () => {
      const view = { center: { lon: 0, lat: 85 }, zoom: 2, width: 800, height: 800 };
      const tiles = visibleTiles(view);
      const tileCount = 2 ** 2;

      tiles.forEach((tile) => {
        expect(tile.y).toBeGreaterThanOrEqual(0);
        expect(tile.y).toBeLessThan(tileCount);
      });
    });

    it('clamps the zoom used for the tile grid to the valid range', () => {
      const view = { center: { lon: 0, lat: 0 }, zoom: 25, width: 300, height: 300 };
      const tiles = visibleTiles(view);
      tiles.forEach((tile) => expect(tile.z).toBe(MAX_ZOOM));
    });
  });

  describe('fitBounds', () => {
    it('returns a close-in zoom for a single point', () => {
      const result = fitBounds([{ lon: -121.9636, lat: 37.3875 }], 800, 600);
      expect(result.center).toEqual({ lon: -121.9636, lat: 37.3875 });
      expect(result.zoom).toBeGreaterThan(MIN_ZOOM);
    });

    it('does not divide by zero when every point is identical', () => {
      const points = [
        { lon: 10, lat: 20 },
        { lon: 10, lat: 20 },
        { lon: 10, lat: 20 },
      ];
      const result = fitBounds(points, 800, 600);

      expect(Number.isFinite(result.zoom)).toBe(true);
      expect(result.center).toEqual({ lon: 10, lat: 20 });
    });

    it('picks a lower zoom for widely separated markers than for nearby ones', () => {
      const nearby = fitBounds(
        [
          { lon: 10, lat: 20 },
          { lon: 10.01, lat: 20.01 },
        ],
        800,
        600,
      );
      const wide = fitBounds(
        [
          { lon: -120, lat: 30 },
          { lon: 120, lat: -30 },
        ],
        800,
        600,
      );

      expect(wide.zoom).toBeLessThan(nearby.zoom);
    });

    it('centers latitude in projected space so high-latitude bounds remain visible', () => {
      const result = fitBounds(
        [
          { lon: 0, lat: 0 },
          { lon: 0, lat: 80 },
        ],
        800,
        600,
      );
      const view = { ...result, width: 800, height: 600 };

      expect(lonLatToScreen(0, 0, view).y).toBeGreaterThanOrEqual(60);
      expect(lonLatToScreen(0, 80, view).y).toBeLessThanOrEqual(540);
    });

    it('clamps the resulting zoom to the valid range', () => {
      const result = fitBounds(
        [
          { lon: -179.9, lat: 89 },
          { lon: 179.9, lat: -89 },
        ],
        800,
        600,
      );

      expect(result.zoom).toBeGreaterThanOrEqual(MIN_ZOOM);
      expect(result.zoom).toBeLessThanOrEqual(MAX_ZOOM);
    });

    it('returns a default view for an empty point list', () => {
      const result = fitBounds([], 800, 600);
      expect(result.center).toEqual({ lon: 0, lat: 0 });
      expect(result.zoom).toBe(MIN_ZOOM);
    });
  });
});
