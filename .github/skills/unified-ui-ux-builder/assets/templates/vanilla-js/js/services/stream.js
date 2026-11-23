/**
 * SPDX-FileCopyrightText: (C) 2026 Intel Corporation
 * SPDX-License-Identifier: Apache-2.0
 *
 * Server-Sent Events stream with reconnect-with-backoff, simplified from
 * the reference app's js/services/metadata-stream.js (which reconnects
 * after a fixed 5s delay on EventSource error). Replace '/api/stream' and
 * the message handler with the target app's real endpoint/payload shape.
 */
const StreamService = (function () {
  const RECONNECT_DELAY_MS = 5000;
  let source = null;
  let reconnectTimer = null;
  let onMessageCallback = null;

  function connect(endpoint, onMessage) {
    onMessageCallback = onMessage;
    source = new EventSource(endpoint);

    source.onopen = () => console.log('Stream connected');

    source.onmessage = (event) => {
      if (!event.data) return;
      try {
        const payload = JSON.parse(event.data);
        if (onMessageCallback) onMessageCallback(payload);
      } catch (err) {
        console.error('Error parsing stream message:', err, event.data);
      }
    };

    source.onerror = (event) => {
      console.error('Stream error:', event);
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        if (source && source.readyState === EventSource.CLOSED) {
          console.log('Reconnecting stream...');
          source = null;
          connect(endpoint, onMessageCallback);
        }
      }, RECONNECT_DELAY_MS);
    };
  }

  function close() {
    if (reconnectTimer) clearTimeout(reconnectTimer);
    if (source) source.close();
    source = null;
    reconnectTimer = null;
  }

  return { connect, close };
})();
