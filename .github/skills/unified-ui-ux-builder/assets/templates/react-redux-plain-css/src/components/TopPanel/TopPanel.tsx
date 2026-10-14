// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
//
// Top navigation bar: app name + nav tabs + connection status.
// See references/component-library.md "Stack B > Header / top bar".

import React from 'react';
import { useAppSelector } from '../../redux/hooks';
import './TopPanel.css';

interface TopPanelProps {
  activeScreen: string;
  setActiveScreen: (screen: string) => void;
}

const TopPanel: React.FC<TopPanelProps> = ({ activeScreen, setActiveScreen }) => {
  const connectionStatus = useAppSelector((state) => state.ui.connectionStatus);

  return (
    <header className="top-panel">
      <div className="top-panel__brand">App Name</div>
      <nav className="top-panel__nav">
        {['main', 'settings'].map((screen) => (
          <button
            key={screen}
            type="button"
            className={`top-panel__nav-item${activeScreen === screen ? ' top-panel__nav-item--active' : ''}`}
            onClick={() => setActiveScreen(screen)}
          >
            {screen}
          </button>
        ))}
      </nav>
      <span className={`top-panel__status top-panel__status--${connectionStatus}`}>
        {connectionStatus}
      </span>
    </header>
  );
};

export default TopPanel;
