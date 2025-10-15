// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { FC, useEffect } from 'react';
import SearchSidebar from './SearchSidebar';
import SearchContent from './SearchContent';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import { SearchLoad, SearchSelector } from '../../redux/search/searchSlice';

export const SearchMainContainer: FC = () => {
  const { triggerLoad } = useAppSelector(SearchSelector);

  const dispatch = useAppDispatch();

  useEffect(() => {
    if (triggerLoad) {
      dispatch(SearchLoad());
    }
  }, [triggerLoad]);

  return (
    <>
      <SearchSidebar />
      <SearchContent />
    </>
  );
};

export default SearchMainContainer;
