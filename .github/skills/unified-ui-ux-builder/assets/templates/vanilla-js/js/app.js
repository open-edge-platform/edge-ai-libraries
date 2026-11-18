/**
 * SPDX-FileCopyrightText: (C) 2026 Intel Corporation
 * SPDX-License-Identifier: Apache-2.0
 *
 * Entry point — wires theme toggle, status polling, and (optionally) a
 * live stream, mirroring the reference app's js/app.js bootstrap. Replace
 * the sample status fetch with the target app's real init sequence.
 */
(function () {
  function init() {
    const themeToggle = document.getElementById('themeToggle');
    const statusEl = document.getElementById('connectionStatus');

    ThemeManager.applyTheme(ThemeManager.detectInitialTheme(), themeToggle);
    themeToggle.addEventListener('click', () => ThemeManager.toggleTheme(themeToggle));

    ApiService.fetchStatus().then((data) => {
      StatusDot.render(statusEl, data.status);
    });

    // Uncomment to subscribe to a live SSE stream:
    // StreamService.connect('/api/stream', (payload) => { ... });
  }

  document.addEventListener('DOMContentLoaded', init);
})();
