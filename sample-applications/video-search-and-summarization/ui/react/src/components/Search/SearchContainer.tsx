// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { FC, useEffect } from 'react';
import SearchSidebar from './SearchSidebar';
import SearchContent from './SearchContent';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import { LoadRefreshConfig, SearchLoad, SearchSelector } from '../../redux/search/searchSlice';

export const SearchMainContainer: FC = () => {
  const { triggerLoad } = useAppSelector(SearchSelector);

  const dispatch = useAppDispatch();

  useEffect(() => {
    if (triggerLoad) {
      dispatch(SearchLoad());
    }
  }, [triggerLoad]);

  // Auto-refresh cadence is owned by the backend; fetch it once so the sidebar
  // can describe the behavior accurately instead of hard-coding an interval.
  useEffect(() => {
    dispatch(LoadRefreshConfig());
  }, [dispatch]);

  return (
    <>
      <SearchSidebar />
      <SearchContent />
    </>
  );
};

export default SearchMainContainer;
