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

const RECONNECT_INITIAL_DELAY_MS = 1000;
const RECONNECT_MAX_DELAY_MS = 30000;
const RECONNECT_BACKOFF_MULTIPLIER = 2;

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
        streamReconnecting(
          `${reason} Reconnecting in ${Math.round(delay / 1000)}s...`,
        ),
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
          dispatch(streamError("Metrics stream closed by upstream."));
          scheduleReconnect("Metrics stream closed.");
        } else {
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
