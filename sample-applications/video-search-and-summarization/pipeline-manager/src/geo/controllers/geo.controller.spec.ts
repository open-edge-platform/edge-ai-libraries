// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Test, TestingModule } from '@nestjs/testing';
import { GeoController } from './geo.controller';
import { GeoService } from '../services/geo.service';
import { GeoIntersectionsRO } from '../models/geo.model';

describe('GeoController', () => {
  let controller: GeoController;
  const payload: GeoIntersectionsRO = {
    source: 'geo-api',
    stale: false,
    fetchedAt: '2026-10-01T00:00:00.000Z',
    intersections: {
      intersection_1: { label: 'One', lat: 1, lon: 2, cameras: {} },
    },
  };
  const geoService = { getIntersections: jest.fn().mockResolvedValue(payload) };

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      controllers: [GeoController],
      providers: [{ provide: GeoService, useValue: geoService }],
    }).compile();
    controller = module.get(GeoController);
  });

  it('returns the intersections from the service', async () => {
    await expect(controller.getIntersections()).resolves.toBe(payload);
    expect(geoService.getIntersections).toHaveBeenCalled();
  });
});
