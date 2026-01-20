import { useEffect, useRef } from "react";
import { useAppDispatch } from "@/store/hooks";
import {
  wsConnecting,
  wsConnected,
  wsDisconnected,
  wsError,
  messageReceived,
} from "@/store/reducers/metrics.ts";

const getWebSocketUrl = () => {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const host = window.location.host;
  return `${protocol}//${host}/metrics/ws/clients`;
};

const WEB_SOCKET_NORMAL_CLOSURE = 1000;

const RECONNECT_CONFIG = {
  initialDelayMs: 1000,
  maxDelayMs: 30000,
  backoffMultiplier: 2,
};

export const useWebSocketConnection = () => {
  const dispatch = useAppDispatch();
  const webSocketRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  const reconnectAttemptRef = useRef(0);
  const isIntentionalCloseRef = useRef(false);

  const clearReconnectTimeout = () => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
  };

  const getReconnectDelay = () =>
    Math.min(
      RECONNECT_CONFIG.initialDelayMs *
        Math.pow(
          RECONNECT_CONFIG.backoffMultiplier,
          reconnectAttemptRef.current,
        ),
      RECONNECT_CONFIG.maxDelayMs,
    );

  const scheduleReconnect = () => {
    if (isIntentionalCloseRef.current) {
      return;
    }

    clearReconnectTimeout();

    const delay = getReconnectDelay();
    console.debug(
      `Scheduling reconnection attempt ${reconnectAttemptRef.current + 1} in ${delay}ms`,
    );

    reconnectTimeoutRef.current = setTimeout(() => {
      reconnectAttemptRef.current += 1;
      connectWebSocket();
    }, delay);
  };

  const connectWebSocket = () => {
    if (
      webSocketRef.current?.readyState === WebSocket.CONNECTING ||
      webSocketRef.current?.readyState === WebSocket.OPEN
    ) {
      return;
    }

    if (webSocketRef.current) {
      webSocketRef.current.close();
    }

    dispatch(wsConnecting());

    try {
      const ws = new WebSocket(getWebSocketUrl());
      webSocketRef.current = ws;

      ws.onopen = () => {
        console.debug("WebSocket connected");
        reconnectAttemptRef.current = 0;
        dispatch(wsConnected());
      };

      ws.onmessage = (event) => {
        dispatch(messageReceived(event.data));
      };

      ws.onerror = (error) => {
        console.error("WebSocket error:", error);
        dispatch(wsError("WebSocket connection error"));
      };

      ws.onclose = (event) => {
        console.debug("WebSocket disconnected", event.code, event.reason);
        dispatch(wsDisconnected());
        webSocketRef.current = null;

        if (
          !isIntentionalCloseRef.current &&
          event.code !== WEB_SOCKET_NORMAL_CLOSURE
        ) {
          scheduleReconnect();
        }
      };
    } catch (error) {
      dispatch(wsError(`Failed to create WebSocket: ${error}`));
      scheduleReconnect();
    }
  };

  useEffect(() => {
    isIntentionalCloseRef.current = false;
    connectWebSocket();

    return () => {
      isIntentionalCloseRef.current = true;
      clearReconnectTimeout();
      if (webSocketRef.current) {
        webSocketRef.current.close();
        webSocketRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return {
    disconnect: () => {
      isIntentionalCloseRef.current = true;
      clearReconnectTimeout();
      if (webSocketRef.current) {
        webSocketRef.current.close();
        webSocketRef.current = null;
      }
    },
    reconnect: () => {
      isIntentionalCloseRef.current = false;
      reconnectAttemptRef.current = 0;
      clearReconnectTimeout();
      connectWebSocket();
    },
  };
};
