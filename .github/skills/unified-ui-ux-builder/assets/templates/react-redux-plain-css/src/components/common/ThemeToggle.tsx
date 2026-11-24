// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
//
// Light/dark theme toggle — must-have baseline element for every reference
// stack (see SKILL.md "Must-have baseline elements"). This stack has no
// next-themes dependency, so this writes `data-theme` on <html> directly
// and persists the choice to localStorage, matching the plain-CSS
// convention documented in references/component-library.md "Stack B".
// Always render this inside TopPanel (see TopPanel.tsx) — it needs the
// `.top-panel .theme-toggle` on-accent override in TopPanel.css to read
// correctly on the blue header bar.

import React, { useEffect, useState } from 'react';
import './ThemeToggle.css';

type Theme = 'light' | 'dark';
const STORAGE_KEY = 'app-theme'; // replace with a per-app key, e.g. '<app>-theme'

function resolveInitialTheme(): Theme {
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (stored === 'light' || stored === 'dark') {
    return stored;
  }
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

const ThemeToggle: React.FC = () => {
  const [theme, setTheme] = useState<Theme>(resolveInitialTheme);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    window.localStorage.setItem(STORAGE_KEY, theme);
  }, [theme]);

  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={() => setTheme((current) => (current === 'light' ? 'dark' : 'light'))}
      aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} theme`}
      title={`Switch to ${theme === 'light' ? 'dark' : 'light'} theme`}
    >
      {theme === 'light' ? '\u{1F319}' : '\u2600\uFE0F'}
    </button>
  );
};

export default ThemeToggle;
