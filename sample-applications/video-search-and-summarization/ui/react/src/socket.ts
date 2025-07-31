// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { io } from 'socket.io-client';
import { APP_URL, SOCKET_APPEND } from './config';
import { CONFIG_STATE } from './utils/constant';

console.log('Append', SOCKET_APPEND);
console.log('URL', APP_URL);

let socketTemp = io({ path: '/ws/' });

if (SOCKET_APPEND == CONFIG_STATE.ON) {
  socketTemp = io(APP_URL, { path: '/ws/' });
}

export const socket = socketTemp;
