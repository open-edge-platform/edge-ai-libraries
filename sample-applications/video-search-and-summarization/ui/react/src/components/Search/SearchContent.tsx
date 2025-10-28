// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { FC } from 'react';
import styled from 'styled-components';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import { useTranslation } from 'react-i18next';
import { Slider, Tag, Tooltip, Button } from '@carbon/react';
import { RerunSearch, SearchActions, SearchSelector } from '../../redux/search/searchSlice';
import { StateActionStatus } from '../../redux/summary/summary';
import { VideoTile } from '../../redux/search/VideoTile';
import { UIActions, uiSelector } from '../../redux/ui/ui.slice';
import VideoGroupsView from '../VideoGroups/VideoGroupsView';

const QueryContentWrapper = styled.div`
  display: flex;
  flex-flow: column nowrap;
  align-items: flex-start;
  justify-content: flex-start;
  overflow: hidden;
  .videos-container {
    display: flex;
    flex-flow: row wrap;
    overflow-x: hidden;
    overflow-y: auto;
    .video-tile {
      position: relative;
      width: 20rem;
      margin: 1rem;
      border: 1px solid rgba(0, 0, 0, 0.2);
      border-radius: 0.5rem;
      overflow: hidden;
      video {
        width: 100%;
      }
      .relevance {
        padding: 1rem;
      }
    }
  }
`;

const QueryHeader = styled.div`
  display: flex;
  flex-flow: row nowrap;
  align-items: center;
  justify-content: flex-start;
  padding: 1rem;
  background-color: var(--color-sidebar);
  position: sticky;
  z-index: 1;
  border-bottom: 1px solid var(--color-border);
  max-height: 3rem;
  width: 100%;
  .cds--form-item {
    flex: none;
  }
  .cds--tooltip-trigger__wrapper {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 32rem;
    flex: 1 1 auto;
  }
`;

const SliderLabel = styled.div`
  margin-right: 1rem;
`;

export const statusClassName = {
  [StateActionStatus.NA]: 'gray',
  [StateActionStatus.READY]: 'purple',
  [StateActionStatus.IN_PROGRESS]: 'blue',
  [StateActionStatus.COMPLETE]: 'green',
};

export const statusClassLabel = {
  [StateActionStatus.NA]: 'naTag',
  [StateActionStatus.READY]: 'readyTag',
  [StateActionStatus.IN_PROGRESS]: 'progressTag',
  [StateActionStatus.COMPLETE]: 'completeTag',
};

const NothingSelectedWrapper = styled.div`
  opacity: 0.6;
  padding: 0 2rem;
`;

const TagsContainer = styled.div`
  display: flex;
  flex-flow: row wrap;
  align-items: center;
  justify-content: flex-start;
  margin-left: 1rem;
  .cds--tag {
    margin: 0.25rem;
  }
`;

const ErrorMessageWrapper = styled.div`
  padding: 1.5rem;
  background-color: #fdf2f2;
  border: 1px solid #da1e28;
  border-radius: 0.5rem;
  margin: 1rem;
  display: flex;
  align-items: flex-start;
  gap: 1rem;
  
  .error-icon {
    font-size: 1.5rem;
    flex-shrink: 0;
  }
  
  .error-content {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  
  .error-title {
    font-weight: 600;
    color: #da1e28;
    font-size: 1.1rem;
  }
  
  .error-text {
    color: #525252;
    line-height: 1.4;
  }
  
  .error-actions {
    display: flex;
    gap: 0.5rem;
    margin-top: 0.5rem;
  }
`;

export const QueryHeading: FC = () => {
  const { selectedQuery, isSelectedInProgress, isSelectedHasError } = useAppSelector(SearchSelector);
  const dispatch = useAppDispatch();
  const { t } = useTranslation();

  const refetchQuery = () => {
    if (selectedQuery) {
      dispatch(RerunSearch(selectedQuery.queryId));
    }
  };

  return (
    <QueryHeader>
      <Tooltip align='bottom' label={selectedQuery?.query}>
        <span className='query-title'>{selectedQuery?.query}</span>
      </Tooltip>
      {selectedQuery && selectedQuery?.tags.length > 0 && (
        <TagsContainer>
          {selectedQuery.tags.map((tag, index) => (
            <Tag key={index} size='sm' type='high-contrast'>
              {tag}
            </Tag>
          ))}
        </TagsContainer>
      )}
      <span className='spacer'></span>
      {isSelectedInProgress && (
        <Tag size='sm' type='blue'>
          {t('searchInProgress')}
        </Tag>
      )}
      {isSelectedHasError && (
        <Tag size='sm' type='red'>
          {t('searchError')}
        </Tag>
      )}
      {selectedQuery && (
        <>
          <SliderLabel>{t('topK')}</SliderLabel>
          <Slider
            min={1}
            max={20}
            step={1}
            value={selectedQuery.topK}
            onChange={({ value }) => {
              dispatch(SearchActions.updateTopK({ queryId: selectedQuery.queryId, topK: value }));
            }}
          />
        </>
      )}
      <Button
        kind='ghost'
        size='sm'
        onClick={() => {
          // toggle the grouped video view on/off
          // eslint-disable-next-line no-console
          console.log('Group by Tag button clicked (toggle)');
          dispatch(UIActions.toggleVideoGroups());
        }}
      >
        {t('GroupByTag')}
      </Button>
      <Button kind='ghost' size='sm' onClick={refetchQuery}>
        Re-run Search
      </Button>
    </QueryHeader>
  );
};

export const SearchContent: FC = () => {
  const { selectedQuery, selectedResults, isSelectedInProgress, isSelectedHasError } = useAppSelector(SearchSelector);
  const { showVideoGroups } = useAppSelector(uiSelector);
  const { t } = useTranslation();
  const dispatch = useAppDispatch();

  const NoQuerySelected = () => {
    return (
      <NothingSelectedWrapper>
        <h3>{t('searchNothingSelected')}</h3>
      </NothingSelectedWrapper>
    );
  };

  const refetchQuery = () => {
    if (selectedQuery) {
      dispatch(RerunSearch(selectedQuery.queryId));
    }
  };

  const QueryHeading = () => {
    return (
      <QueryHeader>
        <Tooltip align='bottom' label={selectedQuery?.query}>
          <span className='query-title'>{selectedQuery?.query}</span>
        </Tooltip>
        {selectedQuery && selectedQuery?.tags.length > 0 && (
          <TagsContainer>
            {selectedQuery.tags.map((tag, index) => (
              <Tag key={index} size='sm' type='high-contrast'>
                {tag}
              </Tag>
            ))}
          </TagsContainer>
        )}
        <span className='spacer'></span>
        {isSelectedInProgress && (
          <Tag size='sm' type='blue'>
            {t('searchInProgress')}
          </Tag>
        )}
        {isSelectedHasError && (
          <Tag size='sm' type='red'>
            {t('searchError')}
          </Tag>
        )}
        {selectedQuery && (
          <>
            <SliderLabel>{t('topK')}</SliderLabel>
            <Slider
              min={1}
              max={20}
              step={1}
              value={selectedQuery.topK}
              onChange={({ value }) => {
                dispatch(SearchActions.updateTopK({ queryId: selectedQuery.queryId, topK: value }));
              }}
            />
          </>
        )}
        <Button
          kind='ghost'
          size='sm'
          onClick={() => {
            console.log('Group by Tag button clicked (toggle)');
            dispatch(UIActions.toggleVideoGroups());
          }}
        >
          {t('GroupByTag')}
        </Button>
        <Button kind='ghost' size='sm' onClick={refetchQuery}>
          Re-run Search
        </Button>
      </QueryHeader>
    );
  };

  const VideosContainer = () => {
    if (selectedResults.length === 0 && selectedQuery && !isSelectedInProgress && !isSelectedHasError) {
      return (
        <div style={{ 
          padding: '2rem', 
          textAlign: 'center', 
          color: '#525252',
          fontStyle: 'italic'
        }}>
          <p>{t('noSearchResults', 'No videos found matching your search query.')}</p>
          <p>{t('tryDifferentSearch', 'Try using different keywords or check if videos have been uploaded.')}</p>
        </div>
      );
    }

    return (
      <>
        <div className='videos-container'>
          {selectedResults.map((_, index) => (
            <VideoTile
              key={`result-${index}`}
              resultIndex={index}
            />
          ))}
        </div>
      </>
    );
  };

  const ErrorMessage = () => {
    if (!selectedQuery?.errorMessage) return null;
    
    return (
      <ErrorMessageWrapper>
        <div className='error-icon'>⚠️</div>
        <div className='error-content'>
          <div className='error-title'>{t('searchErrorTitle', 'Search Failed')}</div>
          <div className='error-text'>{selectedQuery.errorMessage}</div>
        </div>
      </ErrorMessageWrapper>
    );
  };

  return (
    <>
      <QueryContentWrapper>
        {!selectedQuery && <NoQuerySelected />}

        {selectedQuery && (
          <>
            <QueryHeading />
            {showVideoGroups ? (
              <VideoGroupsView />
            ) : (
              isSelectedHasError ? <ErrorMessage /> : <VideosContainer />
            )}
          </>
        )}
      </QueryContentWrapper>
    </>
  );
};

export default SearchContent;