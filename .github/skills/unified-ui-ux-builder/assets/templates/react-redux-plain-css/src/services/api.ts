// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
//
// Thin axios wrapper — mirrors the reference app's src/services/api.ts.
// Keep all backend calls here, not scattered across components.

import axios from 'axios';

const client = axios.create({
  baseURL: '/api',
  timeout: 15000,
});

export interface StatusResponse {
  status: ConnectionStatusLike;
}

type ConnectionStatusLike = 'connected' | 'connecting' | 'disconnected';

export async function fetchStatus(): Promise<StatusResponse> {
  const { data } = await client.get<StatusResponse>('/status');
  return data;
}

export default client;
