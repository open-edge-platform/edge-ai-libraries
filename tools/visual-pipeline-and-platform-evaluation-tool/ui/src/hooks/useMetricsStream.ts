import { useEffect, useRef } from "react";
import { useAppDispatch } from "@/store/hooks";
import {
  streamConnecting,
  streamConnected,
  streamDisconnected,
  streamReconnecting,
  streamError,
  messageReceived,
} from "@/store/reducers/metrics.ts";

const METRICS_STREAM_PATH = "/metrics/stream";

// Exponential backoff bounds for the manual CLOSED-state reconnect path
// below. The browser's native EventSource handles transient transport
// errors on its own, but it gives up permanently when the response
// content-type is not `text/event-stream` (e.g. nginx returns an HTML
// 502 while metrics-service is restarting). We then re-create the
// EventSource ourselves.
const RECONNECT_INITIAL_DELAY_MS = 1000;
const RECONNECT_MAX_DELAY_MS = 30000;
const RECONNECT_BACKOFF_MULTIPLIER = 2;

/**
 * Subscribe to the metrics-service Server-Sent Events stream and dispatch
 * connection-state and message events into the Redux `metrics` slice.
 *
 * The browser's native `EventSource` reconnects automatically after
 * transient transport errors *as long as* the failed response uses
 * `Content-Type: text/event-stream`. When metrics-service is unreachable
 * and nginx returns an HTML `502 Bad Gateway`, EventSource sees a
 * non-SSE response, transitions to `CLOSED` and stops trying. To recover
 * from that case we manually re-create the connection with exponential
 * backoff while the hook is mounted.
 */
export const useMetricsStream = () => {
  const dispatch = useAppDispatch();
  const sourceRef = useRef<EventSource | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  const reconnectAttemptRef = useRef(0);
  const isUnmountedRef = useRef(false);

  useEffect(() => {
    isUnmountedRef.current = false;

    const clearReconnectTimeout = () => {
      if (reconnectTimeoutRef.current !== null) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
    };

    const scheduleReconnect = (reason: string) => {
      if (isUnmountedRef.current) return;
      clearReconnectTimeout();

      const delay = Math.min(
        RECONNECT_INITIAL_DELAY_MS *
          Math.pow(RECONNECT_BACKOFF_MULTIPLIER, reconnectAttemptRef.current),
        RECONNECT_MAX_DELAY_MS,
      );
      reconnectAttemptRef.current += 1;

      dispatch(
        streamReconnecting(`${reason} Reconnecting in ${Math.round(delay / 1000)}s...`),
      );

      reconnectTimeoutRef.current = setTimeout(() => {
        reconnectTimeoutRef.current = null;
        connect();
      }, delay);
    };

    const connect = () => {
      if (isUnmountedRef.current) return;

      // Make sure we never leak a previous EventSource instance.
      sourceRef.current?.close();
      dispatch(streamConnecting());

      const source = new EventSource(METRICS_STREAM_PATH);
      sourceRef.current = source;

      source.onopen = () => {
        reconnectAttemptRef.current = 0;
        dispatch(streamConnected());
      };

      source.onmessage = (event) => {
        dispatch(messageReceived(event.data));
      };

      source.onerror = () => {
        const isClosed = source.readyState === EventSource.CLOSED;
        if (isClosed) {
          // The browser will not reconnect on its own (most often because
          // the failed response was not text/event-stream, e.g. nginx 502
          // while metrics-service is restarting). Drive the reconnect
          // ourselves with exponential backoff.
          dispatch(streamError("Metrics stream closed by upstream."));
          scheduleReconnect("Metrics stream closed.");
        } else {
          // Transport hiccup; the browser's EventSource will auto-reconnect.
          // Reflect that in the store as "connecting" so the UI does not
          // show a hard error state while the connection is being
          // re-established.
          dispatch(
            streamReconnecting("Metrics stream disconnected. Reconnecting..."),
          );
        }
      };
    };

    connect();

    return () => {
      isUnmountedRef.current = true;
      clearReconnectTimeout();
      sourceRef.current?.close();
      sourceRef.current = null;
      dispatch(streamDisconnected());
    };
  }, [dispatch]);

  return {
    disconnect: () => {
      isUnmountedRef.current = true;
      if (reconnectTimeoutRef.current !== null) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      sourceRef.current?.close();
      sourceRef.current = null;
      dispatch(streamDisconnected());
    },
  };
};
