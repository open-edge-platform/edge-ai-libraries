// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { FC } from 'react';
import SummarySidebar from './SummarySideBar';
import Summary from './Summary';

export const SummaryMainContainer: FC = () => {
  return (
    <>
      <SummarySidebar />
      <Summary />
    </>
  );
};

export default SummaryMainContainer;
