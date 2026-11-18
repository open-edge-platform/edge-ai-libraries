/**
 * SPDX-FileCopyrightText: (C) 2026 Intel Corporation
 * SPDX-License-Identifier: Apache-2.0
 *
 * Fetch wrapper for backend REST calls — mirrors the reference app's
 * js/services/api.js shape (IIFE exposing a small set of async methods).
 * Replace fetchStatus with the target app's real endpoints.
 */
const ApiService = (function () {
  async function fetchStatus() {
    try {
      const resp = await fetch('/api/status');
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      return await resp.json();
    } catch (err) {
      console.error('Failed to fetch status', err);
      return { status: 'disconnected' };
    }
  }

  return { fetchStatus };
})();
