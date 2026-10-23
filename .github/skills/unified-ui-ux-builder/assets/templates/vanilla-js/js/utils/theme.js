/**
 * SPDX-FileCopyrightText: (C) 2026 Intel Corporation
 * SPDX-License-Identifier: Apache-2.0
 *
 * Theme management utilities — copied near-verbatim from the reference app
 * (live-video-captioning/app/ui/js/utils/theme.js). Keep this IIFE module
 * pattern (no bundler, no import/export) for every stack C file.
 */
const ThemeManager = (function () {
  const THEME_KEY = 'app-theme';

  function detectInitialTheme() {
    try {
      const saved = localStorage.getItem(THEME_KEY);
      if (saved === 'light' || saved === 'dark') return saved;
    } catch (_err) {
      /* localStorage unavailable (e.g. private browsing) */
    }
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) return 'dark';
    return 'light';
  }

  function applyTheme(theme, themeToggle) {
    const next = theme === 'light' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    if (themeToggle) {
      themeToggle.setAttribute('aria-label', next === 'light' ? 'Switch to dark mode' : 'Switch to light mode');
    }
    try {
      localStorage.setItem(THEME_KEY, next);
    } catch (_err) {
      /* ignore persistence failure */
    }
  }

  function toggleTheme(themeToggle) {
    const current = document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
    applyTheme(current === 'light' ? 'dark' : 'light', themeToggle);
  }

  return { detectInitialTheme, applyTheme, toggleTheme };
})();
