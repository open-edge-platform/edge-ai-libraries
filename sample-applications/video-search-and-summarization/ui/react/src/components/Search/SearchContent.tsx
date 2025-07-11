import { FC } from 'react';
import styled from 'styled-components';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import { useTranslation } from 'react-i18next';
import { Slider, Tooltip } from '@carbon/react';
import { SearchActions, SearchSelector } from '../../redux/search/searchSlice';
import { StateActionStatus } from '../../redux/summary/summary';
import { VideoTile } from '../../redux/search/VideoTile';

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

export const SearchContent: FC = () => {
  const { selectedQuery, selectedResults } = useAppSelector(SearchSelector);
  const dispatch = useAppDispatch();
  const { t } = useTranslation();

  const NoQuerySelected = () => {
    return (
      <NothingSelectedWrapper>
        <h3>{t('searchNothingSelected')}</h3>
      </NothingSelectedWrapper>
    );
  };

  const QueryHeading = () => {
    return (
      <QueryHeader>
        <Tooltip align='bottom' label={selectedQuery?.query}>
          <span className='query-title'>{selectedQuery?.query}</span>
        </Tooltip>
        <span className='spacer'></span>
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
      </QueryHeader>
    );
  };

  const VideosContainer = () => {
    return (
      <>
        <div className='videos-container'>
          {selectedResults.map((curr) => (
            <VideoTile
              key={curr.metadata.id}
              videoId={curr.metadata.video_id}
              relevance={curr.metadata.relevance_score ?? null}
              startTime={curr.metadata.timestamp}
            />
          ))}
        </div>
      </>
    );
  };

  return (
    <>
      <QueryContentWrapper>
        {!selectedQuery && <NoQuerySelected />}

        {selectedQuery && (
          <>
            <QueryHeading />
            <VideosContainer />
          </>
        )}
      </QueryContentWrapper>
    </>
  );
};

export default SearchContent;
