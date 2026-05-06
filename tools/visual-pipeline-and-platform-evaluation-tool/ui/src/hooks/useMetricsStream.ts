import { useEffect, useRef } from "react";
import { useAppDispatch } from "@/store/hooks";
import {
  streamConnecting,
  streamConnected,
  streamDisconnected,
  streamError,
  messageReceived,
} from "@/store/reducers/metrics.ts";

const METRICS_STREAM_PATH = "/metrics/stream";

/**
 * Subscribe to the metrics-service Server-Sent Events stream and dispatch
 * connection-state and message events into the Redux `metrics` slice.
 *
 * Reconnection is delegated to the browser's native `EventSource`
 * implementation (the same pattern used by the pipeline-metadata SSE in
 * `PerformanceTestPanel`). On a transport-level error the browser
 * automatically reconnects every few seconds until `close()` is called.
 */
export const useMetricsStream = () => {
  const dispatch = useAppDispatch();
  const sourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    dispatch(streamConnecting());

    const source = new EventSource(METRICS_STREAM_PATH);
    sourceRef.current = source;

    source.onopen = () => {
      dispatch(streamConnected());
    };

    source.onmessage = (event) => {
      dispatch(messageReceived(event.data));
    };

    source.onerror = () => {
      const isClosed = source.readyState === EventSource.CLOSED;
      if (isClosed) {
        dispatch(streamDisconnected());
      } else {
        // Transport hiccup; browser will auto-reconnect.
        dispatch(streamError("Metrics stream disconnected. Reconnecting..."));
      }
    };

    return () => {
      source.close();
      sourceRef.current = null;
      dispatch(streamDisconnected());
    };
  }, [dispatch]);

  return {
    disconnect: () => {
      sourceRef.current?.close();
      sourceRef.current = null;
      dispatch(streamDisconnected());
    },
  };
};

