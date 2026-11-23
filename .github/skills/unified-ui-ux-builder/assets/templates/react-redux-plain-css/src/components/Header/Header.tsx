// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
//
// Secondary action bar below TopPanel (record/upload/reset style controls).
// See references/component-library.md "Stack B > Header / top bar".

import React from 'react';
import './Header.css';

interface HeaderProps {
  title: string;
  onPrimaryAction?: () => void;
  primaryActionLabel?: string;
}

const Header: React.FC<HeaderProps> = ({ title, onPrimaryAction, primaryActionLabel = 'Start' }) => {
  return (
    <div className="header-bar">
      <h2 className="header-bar__title">{title}</h2>
      {onPrimaryAction && (
        <button type="button" className="header-bar__action" onClick={onPrimaryAction}>
          {primaryActionLabel}
        </button>
      )}
    </div>
  );
};

export default Header;
