// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { contrastWithWhite, hslToRgb, normalizeTags, ResultTags, tagColor } from '../components/Search/ResultTags';

const parseHsl = (color: string): [number, number, number] => {
  const match = /^hsl\((\d+), (\d+)%, (\d+)%\)$/.exec(color);
  expect(match).not.toBeNull();
  const [, h, s, l] = match!.map(Number);
  return [h, s, l];
};

describe('tagColor', () => {
  it('keeps white text legible (WCAG AA) for any tag', () => {
    const tags = Array.from({ length: 2000 }, (_, i) => `tag-${i}-${(i * 7919).toString(36)}`);
    tags.forEach((tag) => {
      const [h, s, l] = parseHsl(tagColor(tag));
      expect(contrastWithWhite(hslToRgb(h, s / 100, l / 100))).toBeGreaterThanOrEqual(4.5);
    });
  });

  it('is stable and ignores case and surrounding spaces', () => {
    expect(tagColor('Parking')).toBe(tagColor('parking'));
    expect(tagColor(' parking ')).toBe(tagColor('parking'));
  });

  it('spreads different tags across hues', () => {
    const tags = ['person', 'car', 'truck', 'bike', 'dog', 'cat', 'parking', 'gate', 'ceramic', 'ketchup'];
    const hues = new Set(tags.map((tag) => parseHsl(tagColor(tag))[0]));
    expect(hues.size).toBe(tags.length);
  });
});

describe('ResultTags', () => {
  it('colours each chip by its tag', () => {
    const { getByText } = render(<ResultTags tags={normalizeTags('car, person')} />);

    expect(getByText('car').style.backgroundColor).not.toBe('');
    expect(getByText('car').style.backgroundColor).not.toBe(getByText('person').style.backgroundColor);
  });

  it('renders nothing without tags', () => {
    const { container } = render(<ResultTags tags={[]} />);
    expect(container.firstChild).toBeNull();
  });
});
