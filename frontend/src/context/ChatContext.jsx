import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useWebSocketContext } from "./WebSocketContext.jsx";

const ChatContext = createContext(null);

export function ChatProvider({ children }) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [streaming, setStreaming] = useState(false);
  const [streamBuffer, setStreamBuffer] = useState("");
  const { sendMessage, addListener } = useWebSocketContext();

  useEffect(() => {
    return addListener((msg) => {
      if (msg.type !== "chat_response") return;
      if (msg.streaming && !msg.done) {
        setStreaming(true);
        setStreamBuffer((prev) => prev + (msg.content || ""));
      } else if (msg.done) {
        setStreaming(false);
        setStreamBuffer((buf) => {
          const content = buf + (msg.content || "");
          if (content) {
            setMessages((m) => [...m, { role: "assistant", content }]);
          }
          return "";
        });
      }
    });
  }, [addListener]);

  const sendChat = useCallback(
    (content) => {
      if (!content.trim()) return;
      setMessages((m) => [...m, { role: "user", content }]);
      setStreaming(true);
      setStreamBuffer("");
      sendMessage({
        type: "chat_message",
        conversation_id: "default",
        content,
      });
    },
    [sendMessage]
  );

  const value = useMemo(
    () => ({ open, setOpen, messages, streaming, streamBuffer, sendChat }),
    [open, messages, streaming, streamBuffer, sendChat]
  );

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
}

export function useChat() {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error("useChat must be used within ChatProvider");
  return ctx;
}
