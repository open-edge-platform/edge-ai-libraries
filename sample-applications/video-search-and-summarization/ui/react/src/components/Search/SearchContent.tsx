// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { FC } from 'react';
import styled from 'styled-components';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import { useTranslation } from 'react-i18next';
import { Slider, Tag, Tooltip, Button, Accordion, AccordionItem } from '@carbon/react';
import { RerunSearch, SearchActions, SearchSelector } from '../../redux/search/searchSlice';
import { TimeFilterSelection } from '../../redux/search/search';
import TimeFilterControl from './TimeFilterControl';
import { StateActionStatus } from '../../redux/summary/summary';
import { VideoTile } from '../../redux/search/VideoTile';
import { UIActions, uiSelector } from '../../redux/ui/ui.slice';
import VideoGroupsView from '../VideoGroups/VideoGroupsView';
import TelemetryAccordion from './TelemetryAccordion';

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

const SettingsContainer = styled.div`
  position: sticky;
  width: 100%;
  top: 0;
  z-index: 2;
  background-color: var(--color-sidebar);
  border-bottom: 1px solid var(--color-border);
  .cds--accordion__item {
    padding-inline-end: 0rem;
  }
`;

const SettingsBar = styled.div`
  display: flex;
  align-items: stretch;
  justify-content: space-between;
  padding: 1rem 0;
  width: 100%;
  gap: 0.75rem;
  flex-wrap: wrap;
`;

const SettingsSection = styled.div`
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex: 1 1 0;
  /* min-width: 10rem; */
`;

const ControlCard = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.75rem;
  border: .1px solid #a8a8a8;
  border-radius: 0.5rem;
  background: #f4f4f4;
`;

const SliderBlock = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  min-width: 8rem;
`;


const QueryBar = styled.div`
  display: flex;
  flex-flow: row wrap;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
  background-color: #f4f4f4;
  border-bottom: 1px solid var(--color-border);
  width: 100%;

  .query-label {
    font-weight: 600;
    color: #525252;
  }

  .query-text {
    font-weight: 700;
    color: #161616;
  }

  .cds--tooltip-trigger__wrapper {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 40rem;
  }
`;

const SliderLabel = styled.div`
  margin-right: 1rem;
`;

const IntervalNotice = styled.div`
  width: 100%;
  padding: 0.5rem 1rem;
  background: #eef4ff;
  color: #0f62fe;
  font-weight: 600;
  border-bottom: 1px solid var(--color-border);
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

export const QuerySettings: FC = () => {
  const { selectedQuery, isSelectedInProgress, isSelectedHasError } = useAppSelector(SearchSelector);
  const dispatch = useAppDispatch();
  const { t } = useTranslation();

  const currentTimeFilter: TimeFilterSelection | null | undefined = selectedQuery?.timeFilter;

  const updateTimeFilter = (timeFilter: TimeFilterSelection | null) => {
    if (!selectedQuery) return;
    dispatch(SearchActions.updateTimeFilter({ queryId: selectedQuery.queryId, timeFilter }));
    dispatch(RerunSearch({ queryId: selectedQuery.queryId, timeFilter }));
  };

  return (
    <SettingsContainer>
      <Accordion align='start' size='sm'>
        <AccordionItem title={t('filters', 'Filters')}>
          <SettingsBar>
            <SettingsSection style={{ justifyContent: 'flex-start' }}>
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
            </SettingsSection>

            <SettingsSection style={{ justifyContent: 'center' }}>
              {selectedQuery && (
                <ControlCard>
                  <SliderBlock>
                    <SliderLabel>{t('searchOutputCount', 'Search Output Count')}</SliderLabel>
                    <Slider
                      min={1}
                      max={20}
                      step={1}
                      value={selectedQuery.topK}
                      hideTextInput
                      onChange={({ value }) => {
                        dispatch(SearchActions.updateTopK({ queryId: selectedQuery.queryId, topK: value }));
                      }}
                    />
                  </SliderBlock>
                </ControlCard>
              )}
            </SettingsSection>

            <SettingsSection style={{ justifyContent: 'flex-end' }}>
              {selectedQuery && (
                <ControlCard>
                  <TimeFilterControl
                    key={selectedQuery.queryId}
                    timeFilter={currentTimeFilter}
                    onChange={updateTimeFilter}
                    idPrefix='time-filter'
                    size='sm'
                  />
                </ControlCard>
              )}
            </SettingsSection>
          </SettingsBar>
        </AccordionItem>
      </Accordion>
    </SettingsContainer>
  );
};

export const QueryInfo: FC = () => {
  const { selectedQuery } = useAppSelector(SearchSelector);
  const dispatch = useAppDispatch();
  const { t } = useTranslation();

  if (!selectedQuery) return null;

  return (
    <QueryBar>
      <span className='query-label'>{t('userQueryLabel', 'User Query:')}</span>
      <Tooltip align='bottom' label={selectedQuery.query}>
        <strong className='query-text'>{selectedQuery.query}</strong>
      </Tooltip>
      {selectedQuery.tags.length > 0 && (
        <TagsContainer>
          {selectedQuery.tags.map((tag, index) => (
            <Tag key={index} size='sm' type='high-contrast'>
              {tag}
            </Tag>
          ))}
        </TagsContainer>
      )}
      <span style={{ flex: 1 }}></span>
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
      <Button
        kind='ghost'
        size='sm'
        onClick={() => {
          dispatch(RerunSearch({ queryId: selectedQuery.queryId, timeFilter: selectedQuery.timeFilter }));
        }}
      >
        Re-run Search
      </Button>
    </QueryBar>
  );
};

export const IntervalDisplay: FC = () => {
  const { selectedQuery } = useAppSelector(SearchSelector);
  if (!selectedQuery || !selectedQuery.timeFilter || !selectedQuery.timeFilter.value || !selectedQuery.timeFilter.unit) {
    return null;
  }

  const { value, unit } = selectedQuery.timeFilter;
  const unitLabel = unit.charAt(0).toUpperCase() + unit.slice(1);

  return <IntervalNotice>{`Time Range: Last ${value} ${unitLabel}`}</IntervalNotice>;
};

const NoQuerySelected: FC = () => <NothingSelectedWrapper></NothingSelectedWrapper>;

const VideosContainer: FC = () => {
  const { selectedQuery, selectedResults, isSelectedInProgress, isSelectedHasError } = useAppSelector(SearchSelector);
  const { t } = useTranslation();

  if (!selectedQuery) return null;

  if (selectedResults.length === 0 && !isSelectedInProgress && !isSelectedHasError) {
    return (
      <div style={{ padding: '2rem', textAlign: 'center', color: '#525252', fontStyle: 'italic' }}>
        <p>{t('noSearchResults', 'No videos found matching your search query.')}</p>
        <p>{t('tryDifferentSearch', 'Try using different keywords or check if videos have been uploaded.')}</p>
      </div>
    );
  }

  if (isSelectedHasError) return null;

  return (
    <div className='videos-container'>
      {selectedResults.map((_, index) => (
        <VideoTile key={`result-${index}`} resultIndex={index} />
      ))}
    </div>
  );
};

const ErrorMessage: FC = () => {
  const { selectedQuery } = useAppSelector(SearchSelector);
  const { t } = useTranslation();
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

export const SearchContent: FC = () => {
  const hasSelectedQuery = useAppSelector((state) => Boolean(SearchSelector(state).selectedQuery));
  const isSelectedHasError = useAppSelector((state) => SearchSelector(state).isSelectedHasError);
  const { showVideoGroups } = useAppSelector(uiSelector);

  return (
    <>
      <QueryContentWrapper>
        {!hasSelectedQuery && <NoQuerySelected />}

        {hasSelectedQuery && (
          <>
            <QuerySettings />
            <QueryInfo />
            <IntervalDisplay />
            {showVideoGroups ? <VideoGroupsView /> : isSelectedHasError ? <ErrorMessage /> : <VideosContainer />}
          </>
        )}
        <TelemetryAccordion />
      </QueryContentWrapper>
    </>
  );
};

export default SearchContent;