// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { type FC } from 'react';

import NotificationList from './components/Notification/NotificationList.tsx';
import MainPage from './components/MainPage/MainPage.tsx';
import './utils/i18n';

const App: FC = () => {
  return (
    <>
      <MainPage />
      <NotificationList />
    </>
  );
};

export default App;
