import { useEffect, useRef, useCallback } from "react";
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

export const useWebSocketConnection = () => {
  const dispatch = useAppDispatch();
  const webSocketRef = useRef<WebSocket | null>(null);

  const connectWebSocket = useCallback(() => {
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
        console.log("WebSocket connected");
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
        console.log("WebSocket disconnected", event.code, event.reason);
        dispatch(wsDisconnected());
        webSocketRef.current = null;
      };
    } catch (error) {
      dispatch(wsError(`Failed to create WebSocket: ${error}`));
    }
  }, [dispatch]);

  useEffect(() => {
    connectWebSocket();

    return () => {
      if (webSocketRef.current) {
        webSocketRef.current.close();
        webSocketRef.current = null;
      }
    };
  }, [connectWebSocket]);

  return {
    disconnect: () => {
      if (webSocketRef.current) {
        webSocketRef.current.close();
        webSocketRef.current = null;
      }
    },
    reconnect: () => {
      connectWebSocket();
    },
  };
};
