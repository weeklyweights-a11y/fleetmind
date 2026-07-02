import { useCallback, useEffect, useRef, useState } from "react";

const WS_URL = import.meta.env.VITE_WS_URL || "ws://localhost:8000/ws";

export function useWebSocket() {
  const [connected, setConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState(null);
  const wsRef = useRef(null);
  const reconnectRef = useRef(null);

  const sendMessage = useCallback((message) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    const connect = () => {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!cancelled) setConnected(true);
      };

      ws.onmessage = (event) => {
        try {
          setLastMessage(JSON.parse(event.data));
        } catch {
          setLastMessage({ raw: event.data });
        }
      };

      ws.onclose = () => {
        setConnected(false);
        if (!cancelled) {
          reconnectRef.current = setTimeout(connect, 2000);
        }
      };

      ws.onerror = () => ws.close();
    };

    connect();

    return () => {
      cancelled = true;
      clearTimeout(reconnectRef.current);
      wsRef.current?.close();
    };
  }, []);

  return { connected, lastMessage, sendMessage };
}
