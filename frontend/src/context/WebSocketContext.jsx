import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

const WS_URL = import.meta.env.VITE_WS_URL || "ws://localhost:8000/ws";

const WebSocketContext = createContext(null);

const BACKOFF = [1000, 2000, 4000, 8000, 16000, 30000];

export function WebSocketProvider({ children }) {
  const [connectionState, setConnectionState] = useState("connecting");
  const [nextRetryIn, setNextRetryIn] = useState(0);
  const wsRef = useRef(null);
  const backoffRef = useRef(0);
  const retryTimerRef = useRef(null);
  const countdownRef = useRef(null);
  const listenersRef = useRef(new Set());
  const pendingTopicsRef = useRef(new Set(["document_status"]));
  const subscribedTopicsRef = useRef(new Set());

  const emit = useCallback((msg) => {
    listenersRef.current.forEach((fn) => fn(msg));
  }, []);

  const flushSubscribe = useCallback(() => {
    const topics = [...pendingTopicsRef.current];
    if (!topics.length || wsRef.current?.readyState !== WebSocket.OPEN) return;
    const toAdd = topics.filter((t) => !subscribedTopicsRef.current.has(t));
    if (!toAdd.length) return;
    wsRef.current.send(JSON.stringify({ type: "subscribe", topics: toAdd }));
    toAdd.forEach((t) => subscribedTopicsRef.current.add(t));
  }, []);

  const subscribe = useCallback((topics, unsubscribe = []) => {
    unsubscribe.forEach((t) => {
      pendingTopicsRef.current.delete(t);
      subscribedTopicsRef.current.delete(t);
    });
    topics.forEach((t) => pendingTopicsRef.current.add(t));
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(
        JSON.stringify({
          type: "subscribe",
          topics: topics.filter((t) => !subscribedTopicsRef.current.has(t)),
          unsubscribe,
        })
      );
      topics.forEach((t) => subscribedTopicsRef.current.add(t));
      unsubscribe.forEach((t) => subscribedTopicsRef.current.delete(t));
    }
  }, []);

  const unsubscribe = useCallback((topics) => {
    topics.forEach((t) => {
      pendingTopicsRef.current.delete(t);
      if (t !== "document_status") subscribedTopicsRef.current.delete(t);
    });
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "unsubscribe", topics }));
      topics.forEach((t) => subscribedTopicsRef.current.delete(t));
    }
  }, []);

  const sendMessage = useCallback((message) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
    }
  }, []);

  const addListener = useCallback((fn) => {
    listenersRef.current.add(fn);
    return () => listenersRef.current.delete(fn);
  }, []);

  const connect = useCallback(() => {
    setConnectionState("connecting");
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      backoffRef.current = 0;
      setConnectionState("connected");
      setNextRetryIn(0);
      subscribedTopicsRef.current.clear();
      pendingTopicsRef.current.add("document_status");
      flushSubscribe();
    };

    ws.onmessage = (event) => {
      try {
        emit(JSON.parse(event.data));
      } catch {
        emit({ raw: event.data });
      }
    };

    ws.onclose = () => {
      setConnectionState("reconnecting");
      subscribedTopicsRef.current.clear();
      const delay = BACKOFF[Math.min(backoffRef.current, BACKOFF.length - 1)];
      backoffRef.current += 1;
      setNextRetryIn(Math.ceil(delay / 1000));
      let remaining = delay;
      clearInterval(countdownRef.current);
      countdownRef.current = setInterval(() => {
        remaining -= 1000;
        setNextRetryIn(Math.max(0, Math.ceil(remaining / 1000)));
      }, 1000);
      retryTimerRef.current = setTimeout(() => {
        clearInterval(countdownRef.current);
        connect();
      }, delay);
    };

    ws.onerror = () => ws.close();
  }, [emit, flushSubscribe]);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(retryTimerRef.current);
      clearInterval(countdownRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  const value = useMemo(
    () => ({
      connectionState,
      nextRetryIn,
      connected: connectionState === "connected",
      subscribe,
      unsubscribe,
      sendMessage,
      addListener,
    }),
    [connectionState, nextRetryIn, subscribe, unsubscribe, sendMessage, addListener]
  );

  return <WebSocketContext.Provider value={value}>{children}</WebSocketContext.Provider>;
}

export function useWebSocketContext() {
  const ctx = useContext(WebSocketContext);
  if (!ctx) throw new Error("useWebSocketContext must be used within WebSocketProvider");
  return ctx;
}
