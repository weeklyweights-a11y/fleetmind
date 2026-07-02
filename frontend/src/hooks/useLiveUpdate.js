import { useEffect } from "react";
import { useWebSocketContext } from "../context/WebSocketContext.jsx";

export function useLiveUpdate(topic, onMessage) {
  const { subscribe, unsubscribe, addListener } = useWebSocketContext();

  useEffect(() => {
    if (!topic) return undefined;
    subscribe([topic]);
    const remove = addListener((msg) => {
      if (msg.type === "data_update" && msg.topic === topic) {
        onMessage?.(msg);
      } else if (msg.type === "document_status" && topic === "document_status") {
        onMessage?.(msg);
      }
    });
    return () => {
      remove();
      unsubscribe([topic]);
    };
  }, [topic, onMessage, subscribe, unsubscribe, addListener]);
}
