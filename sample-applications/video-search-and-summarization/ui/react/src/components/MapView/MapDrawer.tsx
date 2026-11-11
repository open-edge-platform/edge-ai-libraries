// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { FC, useEffect, useMemo, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import styled from 'styled-components';
import { IconButton } from '@carbon/react';
import { Close } from '@carbon/icons-react';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import { SearchSelector } from '../../redux/search/searchSlice';
import { GeoActions, geoSelector } from '../../redux/geo/geoSlice';
import MapView from './MapView';
import { buildIntersectionMarkers, unmappedResultCount, unmappedTags } from './intersectionMarkers';

// In-flow flex item (not position: fixed) so it squeezes the results column
// instead of overlaying it; width animates between 0 and its open size.
const DrawerWrapper = styled.aside<{ $open: boolean }>`
  position: relative;
  flex: 0 0 auto;
  width: ${({ $open }) => ($open ? '50vw' : '0')};
  min-width: ${({ $open }) => ($open ? 'min(28rem, 100vw)' : '0')};
  max-width: 100vw;
  height: 100%;
  background: #ffffff;
  box-shadow: -6px 0 16px rgba(0, 0, 0, 0.18);
  overflow: hidden;
  /* Delay hiding until the slide-out finishes so a closed drawer is not reachable with Tab. */
  visibility: ${({ $open }) => ($open ? 'visible' : 'hidden')};
  transition:
    width 0.3s ease-in-out,
    visibility 0s linear ${({ $open }) => ($open ? '0s' : '0.3s')};
  display: flex;
  flex-direction: column;
  isolation: isolate;

  @media (prefers-reduced-motion: reduce) {
    transition: none;
  }
`;

const DrawerHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  padding: 0.5rem 0.5rem 0.5rem 1rem;
  border-bottom: 1px solid var(--color-border, #e0e0e0);
  font-weight: 600;
`;

const DrawerBody = styled.div`
  position: relative;
  flex: 1 1 0%;
  min-height: 0;
  overflow: hidden;
`;

/** Pins for the selected query's results, one per intersection. */
export const MapResultsContainer: FC = () => {
  const { selectedResults } = useAppSelector(SearchSelector);
  const { intersections, tagIndex, stale } = useAppSelector(geoSelector);

  const markers = useMemo(
    () => buildIntersectionMarkers(selectedResults, intersections, tagIndex),
    [selectedResults, intersections, tagIndex],
  );
  const unmapped = useMemo(
    () => unmappedTags(selectedResults, intersections, tagIndex),
    [selectedResults, intersections, tagIndex],
  );
  const unmappedResults = useMemo(
    () => unmappedResultCount(selectedResults, intersections, tagIndex),
    [selectedResults, intersections, tagIndex],
  );

  return <MapView markers={markers} unmapped={unmapped} unmappedResults={unmappedResults} stale={stale} />;
};

export const MapDrawer: FC = () => {
  const { t } = useTranslation();
  const dispatch = useAppDispatch();
  const hasSelectedQuery = useAppSelector((state) => Boolean(SearchSelector(state).selectedQuery));
  const { hasIntersections, mapDrawerOpen } = useAppSelector(geoSelector);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const drawerRef = useRef<HTMLElement>(null);

  // Close when there is nothing to show, e.g. the query was deleted or no intersection is known any more.
  useEffect(() => {
    if (mapDrawerOpen && (!hasSelectedQuery || !hasIntersections)) {
      dispatch(GeoActions.closeMapDrawer());
    }
  }, [mapDrawerOpen, hasSelectedQuery, hasIntersections, dispatch]);

  useEffect(() => {
    if (!mapDrawerOpen) return undefined;
    const drawer = drawerRef.current;
    const opener = document.activeElement as HTMLElement | null;
    closeButtonRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') dispatch(GeoActions.closeMapDrawer());
    };
    // Capture phase: the focused close button's tooltip would otherwise consume the first Escape.
    window.addEventListener('keydown', onKeyDown, true);
    return () => {
      window.removeEventListener('keydown', onKeyDown, true);
      if (drawer?.contains(document.activeElement)) opener?.focus();
    };
  }, [mapDrawerOpen, dispatch]);

  return (
    <DrawerWrapper
      ref={drawerRef}
      id='map-drawer'
      $open={mapDrawerOpen}
      aria-hidden={!mapDrawerOpen}
      aria-label={t('MapDrawerTitle')}
      data-testid='map-drawer'
    >
      <DrawerHeader>
        <span>{t('MapDrawerTitle')}</span>
        <IconButton
          ref={closeButtonRef}
          kind='ghost'
          size='sm'
          label={t('CloseMap')}
          onClick={() => dispatch(GeoActions.closeMapDrawer())}
        >
          <Close />
        </IconButton>
      </DrawerHeader>
      {/* Mounted only while open so no map tiles are requested for a closed drawer. */}
      <DrawerBody>{mapDrawerOpen && <MapResultsContainer />}</DrawerBody>
    </DrawerWrapper>
  );
};

export default MapDrawer;
