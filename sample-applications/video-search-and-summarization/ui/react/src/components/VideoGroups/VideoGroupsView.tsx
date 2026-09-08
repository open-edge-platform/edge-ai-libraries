// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { FC, useEffect, useMemo, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import styled from 'styled-components';
import { InlineLoading } from '@carbon/react';
import { useAppSelector } from '../../redux/store';
import { ScoreBreakdown, SearchResult } from '../../redux/search/search';
import { videosSelector } from '../../redux/video/videoSlice';
import { SearchSelector } from '../../redux/search/searchSlice';
import { ASSETS_ENDPOINT } from '../../config';
import { resolveSearchResultVideoUrl, resolveVideoUrl } from '../../redux/video/videoUrl';
import { ScoreDisplay } from '../Search/ScoreDisplay';

const VideoGroupsContainer = styled.div`
  padding: 1rem;
  width: 100%;
  height: 100%;
  overflow-y: auto;
  background-color: var(--color-gray-0);
`;

const GroupHeader = styled.h2`
  margin-bottom: 1rem;
  color: var(--color-dark-7);
  font-size: 1.5rem;
  font-weight: 600;
`;

const TagGroup = styled.div<{ $backgroundColor: string }>`
  margin-bottom: 2rem;
  padding: 1.5rem;
  border-radius: 8px;
  background-color: ${({ $backgroundColor }) => $backgroundColor};
  border: 2px solid ${({ $backgroundColor }) => $backgroundColor};
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
`;

const TagHeader = styled.h3`
  margin-bottom: 1rem;
  color: var(--color-dark-7);
  font-size: 1.2rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 0.5rem;
`;

const TagBadge = styled.span`
  background-color: rgba(255, 255, 255, 0.8);
  padding: 0.25rem 0.75rem;
  border-radius: 12px;
  font-size: 0.875rem;
  font-weight: 500;
`;

const VideoGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 1rem;
`;

const VideoCard = styled.div`
  background: rgba(255, 255, 255, 0.9);
  border-radius: 8px;
  padding: 1rem;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.3);
  transition: transform 0.2s ease, box-shadow 0.2s ease;

  &:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  }
`;

const VideoPlayer = styled.video`
  width: 100%;
  height: 200px;
  object-fit: cover;
  border-radius: 4px;
  margin-bottom: 0.5rem;
  background-color: var(--color-gray-2);
`;

const VideoPlaceholder = styled.div`
  width: 100%;
  height: 200px;
  background-color: var(--color-gray-2);
  border-radius: 4px;
  margin-bottom: 0.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-gray-6);
  font-size: 0.875rem;
`;

const VideoTag = styled.span`
  background-color: var(--color-info);
  color: white;
  padding: 0.125rem 0.5rem;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 400;
`;

const TimestampBadge = styled.span`
  background-color: var(--color-dark-7, #343a3f);
  color: white;
  padding: 0.125rem 0.5rem;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
`;

const RelevanceScore = styled.div`
  color: var(--color-text-primary);
  padding: 0.25rem 0.5rem;
  margin-right: 0.5rem;
  font-size: 0.85rem;
  font-weight: 600;
`;

const VideoCardWrapper = styled.div`
  position: relative;
`;

const BottomInfo = styled.div`
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.25rem;
  margin-top: 0.5rem;
`;

const EmptyState = styled.div`
  text-align: center;
  padding: 3rem;
  color: var(--color-gray-7);
`;

// Predefined color palette for tag groups
const TAG_COLORS = [
  '#E3F2FD', // Light Blue
  '#F3E5F5', // Light Purple
  '#E8F5E8', // Light Green
  '#FFF3E0', // Light Orange
  '#FCE4EC', // Light Pink
  '#F1F8E9', // Light Lime
  '#E0F2F1', // Light Teal
  '#FFF8E1', // Light Yellow
  '#EFEBE9', // Light Brown
  '#F5F5F5', // Light Grey
];

/**
 * A single search hit (one clip of one video at one timestamp).
 *
 * Grouping is done per search result rather than per video: a query can return
 * many hits from the same video at different timestamps, and every one of them
 * must stay visible, exactly as in the ungrouped result list.
 */
interface SearchClip {
  /** Stable identity of the search hit, unique even within one video. */
  key: string;
  videoId: string;
  name: string;
  url: string;
  tags: string[];
  timestamp: number;
  relevanceScore: number;
  scoreBreakdown?: ScoreBreakdown;
}

interface TagGroup {
  tag: string;
  clips: SearchClip[];
  videoCount: number;
  color: string;
}

const formatTimestamp = (seconds: number): string => {
  if (!Number.isFinite(seconds) || seconds < 0) return '00:00';
  const total = Math.floor(seconds);
  const mins = Math.floor(total / 60);
  const secs = total % 60;
  return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
};

/** Tag entries can arrive as plain strings or as objects from the search index. */
interface TagObject {
  tag?: unknown;
  name?: unknown;
  label?: unknown;
}

/**
 * Search metadata as consumed here. `SearchResult['metadata']` is typed against
 * the interval-based index, but the frame/crop index adds and omits fields, so
 * everything this view reads is treated as optional.
 */
type ClipMetadata = Partial<SearchResult['metadata']> & {
  title?: string;
  name?: string;
};

/** Normalize `metadata.tags`, which may be an array, a CSV string, or objects. */
const normalizeTags = (rawTags: unknown): string[] => {
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

interface ClipCardProps {
  clip: SearchClip;
  resolvedUrl: string;
}

/**
 * Renders one search hit and seeks the player to the hit's timestamp.
 *
 * The seek has to be driven by `loadedmetadata` because `load()` resets
 * `currentTime` and duration is unknown until the container is parsed. This
 * mirrors the ungrouped `VideoTile` behavior.
 */
const ClipCard: FC<ClipCardProps> = ({ clip, resolvedUrl }) => {
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const videoEl = videoRef.current;
    if (!videoEl || !resolvedUrl) return undefined;

    const seekToTimestamp = () => {
      if (clip.timestamp > 0 && Number.isFinite(videoEl.duration)) {
        videoEl.currentTime = Math.min(clip.timestamp, Math.max(videoEl.duration - 0.1, 0));
      }
    };

    videoEl.addEventListener('loadedmetadata', seekToTimestamp);
    videoEl.load();

    return () => videoEl.removeEventListener('loadedmetadata', seekToTimestamp);
  }, [resolvedUrl, clip.timestamp]);

  return (
    <VideoCard>
      <VideoCardWrapper>
        {resolvedUrl ? (
          <VideoPlayer ref={videoRef} controls preload='metadata'>
            <source src={resolvedUrl} type='video/mp4' />
            Your browser does not support the video tag.
          </VideoPlayer>
        ) : (
          <VideoPlaceholder>Video not available</VideoPlaceholder>
        )}
      </VideoCardWrapper>

      <BottomInfo>
        <RelevanceScore>
          <ScoreDisplay relevanceScore={clip.relevanceScore} scoreBreakdown={clip.scoreBreakdown} />
        </RelevanceScore>
        <TimestampBadge>{formatTimestamp(clip.timestamp)}</TimestampBadge>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.25rem' }}>
          {clip.tags.map((tag, idx) => (
            <VideoTag key={`${clip.key}-tag-${idx}-${tag}`}>{tag}</VideoTag>
          ))}
        </div>
      </BottomInfo>
    </VideoCard>
  );
};

export const VideoGroupsView: FC = () => {
  const { t } = useTranslation();
  const { getVideoUrl } = useAppSelector(videosSelector);
  const { selectedResults, isSelectedInitialLoading } = useAppSelector(SearchSelector);

  // One clip per search result, so hits from the same video at different
  // timestamps are all preserved.
  const searchClips: SearchClip[] = useMemo(() => {
    if (!selectedResults || selectedResults.length === 0) return [];

    // Stable, position-independent keys so refreshing a watched query does not remount
    // clips that are still in the result set. Identical video/timestamp pairs are rare
    // but get a suffix so React keys stay unique.
    const seen = new Map<string, number>();

    return selectedResults
      .map((result: SearchResult) => {
        const meta: ClipMetadata = result.metadata ?? {};
        const videoId = meta.video_id || meta.id;
        if (!videoId) return null;

        const timestamp = typeof meta.timestamp === 'number' ? meta.timestamp : 0;
        const baseKey = `${videoId}-${timestamp}`;
        const occurrence = seen.get(baseKey) ?? 0;
        seen.set(baseKey, occurrence + 1);

        return {
          key: occurrence === 0 ? baseKey : `${baseKey}-${occurrence}`,
          videoId,
          name: meta.name ?? meta.title ?? videoId,
          // Fall back to the object store directly. The dataprep download URLs in
          // metadata are not browser-addressable and do not support ranges.
          url:
            resolveVideoUrl(result.video, ASSETS_ENDPOINT) ||
            resolveSearchResultVideoUrl(meta, ASSETS_ENDPOINT) ||
            '',
          tags: normalizeTags(meta.tags),
          timestamp,
          relevanceScore: typeof meta.relevance_score === 'number' ? meta.relevance_score : 0,
          scoreBreakdown: meta.score_breakdown as ScoreBreakdown | undefined,
        } as SearchClip;
      })
      .filter((clip: SearchClip | null): clip is SearchClip => clip !== null);
  }, [selectedResults]);

  const tagGroups: TagGroup[] = useMemo(() => {
    const groups = new Map<string, SearchClip[]>();

    const addToGroup = (tag: string, clip: SearchClip) => {
      if (!groups.has(tag)) groups.set(tag, []);
      groups.get(tag)!.push(clip);
    };

    searchClips.forEach((clip) => {
      if (clip.tags.length === 0) {
        addToGroup('Untagged', clip);
      } else {
        clip.tags.forEach((tag) => addToGroup(tag, clip));
      }
    });

    return Array.from(groups.entries()).map(([tag, clips], i) => ({
      tag,
      clips: [...clips].sort((a, b) => b.relevanceScore - a.relevanceScore),
      videoCount: new Set(clips.map((clip) => clip.videoId)).size,
      color: TAG_COLORS[i % TAG_COLORS.length],
    }));
  }, [searchClips]);

  // First run of the query: show placeholders rather than a misleading "no results" state.
  // A refresh keeps its existing groups mounted and relies on the QueryInfo chip instead.
  if (isSelectedInitialLoading) {
    return (
      <VideoGroupsContainer data-testid='video-groups-skeleton'>
        <GroupHeader>{t('VideoGroups', 'Video Groups by Tags')}</GroupHeader>
        <EmptyState>
          <InlineLoading status='active' description={t('searchRunning')} />
        </EmptyState>
      </VideoGroupsContainer>
    );
  }

  // If no search results, show a helpful empty state
  if (!selectedResults || selectedResults.length === 0) {
    return (
      <VideoGroupsContainer>
        <GroupHeader>{t('VideoGroups', 'Video Groups by Tags')}</GroupHeader>
        <EmptyState>
          <h3>{t('NoSearchResults', 'No Search Results')}</h3>
          <p>{t('NoSearchResultsDescription', 'Please run a search to see grouped results by tag.')}</p>
        </EmptyState>
      </VideoGroupsContainer>
    );
  }

  if (tagGroups.length === 0) {
    return (
      <VideoGroupsContainer>
        <GroupHeader>{t('VideoGroups', 'Video Groups by Tags')}</GroupHeader>
        <EmptyState>
          <h3>{t('NoTaggedVideos', 'No Tagged Videos')}</h3>
          <p>{t('NoTaggedVideosDescription', 'The search returned results but none have tags to group by.')}</p>
        </EmptyState>
      </VideoGroupsContainer>
    );
  }

  return (
    <VideoGroupsContainer>
      <GroupHeader>{t('VideoGroups', 'Video Groups by Tags')}</GroupHeader>

      {tagGroups.map((group) => (
        <TagGroup key={group.tag} $backgroundColor={group.color}>
          <TagHeader>
            {group.tag}
            <TagBadge>{group.videoCount} videos</TagBadge>
            <TagBadge>{group.clips.length} results</TagBadge>
          </TagHeader>

          <VideoGrid>
            {group.clips.map((clip) => {
              const reduxVideoUrl = getVideoUrl ? getVideoUrl(clip.videoId) : null;
              return (
                <ClipCard
                  key={`${group.tag}-${clip.key}`}
                  clip={clip}
                  resolvedUrl={reduxVideoUrl || clip.url}
                />
              );
            })}
          </VideoGrid>
        </TagGroup>
      ))}
    </VideoGroupsContainer>
  );
};

export default VideoGroupsView;
