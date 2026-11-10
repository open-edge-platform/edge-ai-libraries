// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
//
// Thin API client — one function per backend endpoint. Base URL comes from
// Vite's dev proxy (see vite.config.js) in development and from the same
// origin in production (served behind the same reverse proxy as the backend).

const BASE = '/api';

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) {
    throw new Error(`Request to ${path} failed: ${res.status} ${res.statusText}`);
  }
  const contentType = res.headers.get('content-type') || '';
  return contentType.includes('application/json') ? res.json() : res.text();
}

// Replace with the target app's real endpoints, e.g.:
// export const listItems = () => request('/items');
// export const createItem = (body) => request('/items', { method: 'POST', body: JSON.stringify(body) });

export { request };
