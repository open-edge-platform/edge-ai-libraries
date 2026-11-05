// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { FC } from 'react';
import styled from 'styled-components';

/** Tag entries can arrive as plain strings or as objects from the search index. */
interface TagObject {
  tag?: unknown;
  name?: unknown;
  label?: unknown;
}

/** Normalize `metadata.tags`, which may be an array, a CSV string, or objects. */
export const normalizeTags = (rawTags: unknown): string[] => {
  let entries: unknown[] = [];
  if (Array.isArray(rawTags)) {
    entries = rawTags;
  } else if (typeof rawTags === 'string' && rawTags.trim()) {
    entries = rawTags.split(',');
  }

  return entries
    .map((entry) => {
      if (typeof entry === 'string') return entry.trim();
      if (entry && typeof entry === 'object') {
        const { tag, name, label } = entry as TagObject;
        const tagValue = tag ?? name ?? label ?? '';
        return typeof tagValue === 'string' ? tagValue.trim() : '';
      }
      return String(entry ?? '').trim();
    })
    .filter((tag) => tag.length > 0);
};

/** WCAG AA contrast for normal text. */
const MIN_CONTRAST_WITH_WHITE = 4.5;
const tagColorCache = new Map<string, string>();

/** 32-bit FNV-1a: cheap, stable across sessions, and well spread for short strings. */
const hashString = (value: string): number => {
  let hash = 0x811c9dc5;
  for (let i = 0; i < value.length; i++) {
    hash ^= value.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
};

export const hslToRgb = (h: number, s: number, l: number): [number, number, number] => {
  const a = s * Math.min(l, 1 - l);
  const f = (n: number) => {
    const k = (n + h / 30) % 12;
    return l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1));
  };
  return [f(0), f(8), f(4)];
};

const relativeLuminance = ([r, g, b]: [number, number, number]): number => {
  const lin = (c: number) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
};

export const contrastWithWhite = (rgb: [number, number, number]): number => 1.05 / (relativeLuminance(rgb) + 0.05);

/**
 * A stable colour for a tag: the hue (and a little saturation/lightness jitter)
 * comes from a hash of the tag, so any number of tags get spread-out colours and
 * the same tag looks the same everywhere. Lightness is then lowered until white
 * text meets WCAG AA, since yellows/greens are much brighter than blues at the
 * same HSL lightness.
 */
export const tagColor = (tag: string): string => {
  const key = tag.trim().toLowerCase();
  const cached = tagColorCache.get(key);
  if (cached) return cached;

  const hash = hashString(key);
  const hue = hash % 360;
  const saturation = 55 + ((hash >>> 9) % 25);
  let lightness = 38 + ((hash >>> 17) % 12);
  while (
    lightness > 10 &&
    contrastWithWhite(hslToRgb(hue, saturation / 100, lightness / 100)) < MIN_CONTRAST_WITH_WHITE
  ) {
    lightness -= 1;
  }

  const color = `hsl(${hue}, ${saturation}%, ${lightness}%)`;
  tagColorCache.set(key, color);
  return color;
};

const TagList = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
`;

const TagChip = styled.span`
  color: white;
  padding: 0.125rem 0.5rem;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 400;
`;

export interface ResultTagsProps {
  tags: string[];
  className?: string;
}

/** A search hit's tags as chips; renders nothing when there are none. */
export const ResultTags: FC<ResultTagsProps> = ({ tags, className }) => {
  if (tags.length === 0) return null;
  return (
    <TagList className={className} data-testid='result-tags'>
      {tags.map((tag, idx) => (
        <TagChip key={`${idx}-${tag}`} style={{ backgroundColor: tagColor(tag) }}>
          {tag}
        </TagChip>
      ))}
    </TagList>
  );
};
