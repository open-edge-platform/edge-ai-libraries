// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { FC, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import styled from 'styled-components';
import { useAppSelector } from '../../redux/store';
import { Video } from '../../redux/video/video';
import { videosSelector } from '../../redux/video/videoSlice';
import { SearchSelector } from '../../redux/search/searchSlice';

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

interface TagGroup {
  tag: string;
  videos: Video[];
  color: string;
}

export const VideoGroupsView: FC = () => {
  const { t } = useTranslation();
  const { getVideoUrl } = useAppSelector(videosSelector);
  const { selectedResults } = useAppSelector(SearchSelector);

  // Build a map of relevance scores from search results
  const videoRelevanceMap = useMemo(() => {
    const map = new Map<string, number>();
    selectedResults?.forEach((result) => {
      const vid = result.metadata?.video_id;
      const score = result.metadata?.relevance_score;
      if (vid && typeof score === 'number') map.set(vid, score);
    });
    return map;
  }, [selectedResults]);

  // Convert selected results into minimal Video objects for grouping
  const searchVideos: Video[] = useMemo(() => {
    if (!selectedResults || selectedResults.length === 0) return [];
    return selectedResults
      .map((result) => {
        const meta: any = result.metadata ?? {};
        const vid = meta.video_id || meta.id;
        if (!vid) return null;

        // Normalize tags: can be array or comma-separated string or array of objects
        let tagsArrRaw: any[] = [];
        if (Array.isArray(meta.tags)) {
          tagsArrRaw = meta.tags;
        } else if (typeof meta.tags === 'string' && meta.tags.trim()) {
          tagsArrRaw = meta.tags.split(',').map((s: string) => s.trim()).filter(Boolean);
        }

        // Convert any tag entry into a safe string
        const tagsArr: string[] = tagsArrRaw
          .map((t) => {
            if (typeof t === 'string') return t.trim();
            if (t && typeof t === 'object') {
              const tagValue = t.tag ?? t.name ?? t.label ?? '';
              return typeof tagValue === 'string' ? tagValue.trim() : '';
            }
            return String(t || '').trim();
          })
          .filter((s) => s && s.length > 0); // More strict filtering

        return {
          videoId: vid,
          name: meta.name ?? meta.title ?? vid,
          url: '',
          tags: tagsArr,
          createdAt: (meta.date_time as string) ?? (meta.date as string) ?? '',
          updatedAt: '',
        } as Video;
      })
      .filter((v): v is Video => v !== null);
  }, [selectedResults]);

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

  // Group the converted videos by tag
  const tagGroups: TagGroup[] = useMemo(() => {
    const groups = new Map<string, Video[]>();
    
    searchVideos.forEach((video) => {
      const tags = Array.isArray(video.tags) ? video.tags : [];
      // Filter out any empty or whitespace-only tags
      const validTags = tags.filter((tag) => tag && typeof tag === 'string' && tag.trim().length > 0);
      
      if (validTags.length === 0) {
        // Video has no valid tags - add to Untagged group
        if (!groups.has('Untagged')) groups.set('Untagged', []);
        groups.get('Untagged')!.push(video);
      } else {
        // Video has valid tags - add to each tag group
        validTags.forEach((tag) => {
          const trimmedTag = tag.trim();
          if (!groups.has(trimmedTag)) groups.set(trimmedTag, []);
          groups.get(trimmedTag)!.push(video);
        });
      }
    });

    const arr = Array.from(groups.entries()).map(([tag, vids], i) => ({
      tag,
      videos: vids.sort((a, b) => {
        const sa = videoRelevanceMap.get(a.videoId) ?? 0;
        const sb = videoRelevanceMap.get(b.videoId) ?? 0;
        return sb - sa; // descending
      }),
      color: TAG_COLORS[i % TAG_COLORS.length],
    }));
    return arr;
  }, [searchVideos, videoRelevanceMap]);

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
            <TagBadge>{group.videos.length} videos</TagBadge>
          </TagHeader>

          <VideoGrid>
            {group.videos.map((video) => {
              const videoUrl = getVideoUrl ? getVideoUrl(video.videoId) : video.url;
              const relevanceScore = videoRelevanceMap.get(video.videoId) ?? 0;

              return (
                <VideoCard key={video.videoId}>
                  <VideoCardWrapper>
                    {videoUrl ? (
                      <VideoPlayer controls preload="metadata">
                        <source src={videoUrl} type="video/mp4" />
                        Your browser does not support the video tag.
                      </VideoPlayer>
                    ) : (
                      <VideoPlaceholder>Video not available</VideoPlaceholder>
                    )}
                  </VideoCardWrapper>

                  <BottomInfo>
                    <RelevanceScore>Relevance Score: {relevanceScore.toFixed(3)}</RelevanceScore>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.25rem' }}>
                      {Array.isArray(video.tags) && video.tags.map((rawTag, idx) => {
                        const tAny: any = rawTag;
                        const displayTag = typeof rawTag === 'string'
                          ? rawTag
                          : tAny && typeof tAny === 'object'
                            ? tAny.tag ?? tAny.name ?? tAny.label ?? JSON.stringify(tAny)
                            : String(rawTag);
                        const key = `${video.videoId}-tag-${idx}-${displayTag}`;
                        return <VideoTag key={key}>{displayTag}</VideoTag>;
                      })}
                    </div>
                  </BottomInfo>
                </VideoCard>
              );
            })}
          </VideoGrid>
        </TagGroup>
      ))}
    </VideoGroupsContainer>
  );
};

export default VideoGroupsView;