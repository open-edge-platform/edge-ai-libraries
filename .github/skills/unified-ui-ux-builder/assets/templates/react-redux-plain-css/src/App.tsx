// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
//
// Example page wiring TopPanel -> Header -> split Body (see
// references/layout-patterns.html pattern 3). Replace sample content with
// the target app's real screens; add more slices/services as needed.

import React, { useState } from 'react';
import TopPanel from './components/TopPanel/TopPanel';
import Header from './components/Header/Header';
import Body from './components/common/Body';

const App: React.FC = () => {
  const [activeScreen, setActiveScreen] = useState('main');

  return (
    <div className="app">
      <TopPanel activeScreen={activeScreen} setActiveScreen={setActiveScreen} />
      <Header title="App Name" onPrimaryAction={() => {}} primaryActionLabel="Start" />
      <Body />
    </div>
  );
};

export default App;
