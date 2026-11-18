/**
 * SPDX-FileCopyrightText: (C) 2026 Intel Corporation
 * SPDX-License-Identifier: Apache-2.0
 *
 * Small reusable status-indicator component. See
 * references/component-library.md "Stack C > Status pill".
 */
const StatusDot = (function () {
  function render(el, status) {
    const safe = ['connected', 'connecting', 'disconnected'].includes(status) ? status : 'disconnected';
    el.textContent = safe;
    el.className = `status-dot status-dot--${safe}`;
  }

  return { render };
})();
