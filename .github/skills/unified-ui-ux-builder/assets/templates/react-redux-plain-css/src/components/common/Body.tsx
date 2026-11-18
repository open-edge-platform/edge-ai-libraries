// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
//
// Split-panel layout (left config panel / right results panel), simplified
// from the reference app's src/components/common/Body.tsx — the real app
// adds a draggable divider (see usePanelDividerX); this starter keeps a
// fixed split and a simple collapse toggle instead.
// See references/layout-patterns.html pattern 3 ("Split config/results").

import React from 'react';
import { useAppDispatch, useAppSelector } from '../../redux/hooks';
import { toggleRightPanel } from '../../redux/slices/uiSlice';
import Accordion from './Accordion';
import './Body.css';

const Body: React.FC = () => {
  const dispatch = useAppDispatch();
  const isRightPanelCollapsed = useAppSelector((state) => state.ui.isRightPanelCollapsed);

  return (
    <div className="body-split">
      <div className="body-split__left">
        <Accordion title="Settings" defaultOpen>
          Replace with the app's real configuration controls.
        </Accordion>
        <Accordion title="Advanced">Replace with secondary/advanced settings.</Accordion>
      </div>
      <div
        className="body-split__right"
        style={{ flex: isRightPanelCollapsed ? 0 : 1 }}
      >
        <p>Replace with the app's results/output panel.</p>
      </div>
      <button
        type="button"
        className="body-split__arrow"
        onClick={() => dispatch(toggleRightPanel())}
      >
        {isRightPanelCollapsed ? '\u25C0' : '\u25B6'}
      </button>
    </div>
  );
};

export default Body;
