// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { BadRequestException } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { SearchConfigService } from './search-config.service';

const build = (raw: unknown) =>
  new SearchConfigService({
    get: jest.fn().mockReturnValue(raw),
  } as unknown as ConfigService);

describe('SearchConfigService', () => {
  it.each([
    [undefined, 0],
    ['', 0],
    ['0.2', 0.2],
    ['1', 1],
    ['-0.1', 0],
    ['1.5', 0],
    ['abc', 0],
  ])('reads SEARCH_MIN_PEAK_SCORE=%p as default %p', (raw, expected) => {
    expect(build(raw).getConfig()).toEqual({ minPeakScoreDefault: expected });
  });

  it('accepts unset or in-range values and rejects anything else', () => {
    const service = build(undefined);

    expect(service.parseMinPeakScore(undefined)).toBeUndefined();
    expect(service.parseMinPeakScore(null)).toBeUndefined();
    expect(service.parseMinPeakScore(0)).toBe(0);
    expect(service.parseMinPeakScore(0.125)).toBe(0.125);
    for (const bad of [-0.01, 1.01, '0.2', Number.NaN, Infinity]) {
      expect(() => service.parseMinPeakScore(bad)).toThrow(BadRequestException);
    }
  });

  it('resolves to the first set value, else the default', () => {
    const service = build('0.3');

    expect(service.resolveMinPeakScore(0.1, 0.5)).toBe(0.1);
    expect(service.resolveMinPeakScore(undefined, 0)).toBe(0);
    expect(service.resolveMinPeakScore(undefined, null)).toBe(0.3);
    expect(service.resolveMinPeakScore()).toBe(0.3);
  });
});
