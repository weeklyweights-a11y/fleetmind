import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { apiGet } from "../api/client.js";
import { useWebSocketContext } from "./WebSocketContext.jsx";
import { useDashboardContext } from "./DashboardContext.jsx";

const STORAGE_KEY = "fleetmind_chat";
const ChatContext = createContext(null);

function loadStoredSession() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed.expiresAt && Date.parse(parsed.expiresAt) < Date.now()) {
      sessionStorage.removeItem(STORAGE_KEY);
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

export function ChatProvider({ children }) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [streaming, setStreaming] = useState(false);
  const [streamBuffer, setStreamBuffer] = useState("");
  const [conversationId, setConversationId] = useState(null);
  const [resumed, setResumed] = useState(false);
  const [prefill, setPrefill] = useState("");
  const chatStartedRef = useRef(false);
  const endSentRef = useRef(false);
  const { sendMessage, addListener, connected } = useWebSocketContext();
  const dashboardContext = useDashboardContext();

  useEffect(() => {
    return addListener((msg) => {
      if (msg.type === "chat_started") {
        setConversationId(msg.conversation_id);
        setResumed(!!msg.resumed);
        chatStartedRef.current = true;
        endSentRef.current = false;
        sessionStorage.setItem(
          STORAGE_KEY,
          JSON.stringify({
            conversationId: msg.conversation_id,
            expiresAt: new Date(Date.now() + 86400000).toISOString(),
          })
        );
        if (msg.resumed && msg.conversation_id) {
          apiGet(`/api/conversations/${msg.conversation_id}/messages`)
            .then((rows) =>
              setMessages(
                rows.map((r) => ({
                  role: r.role,
                  content: r.content,
                  tools_used: r.tools_called,
                }))
              )
            )
            .catch(() => {});
        }
        return;
      }
      if (msg.type !== "chat_response") return;
      if (conversationId && msg.conversation_id && msg.conversation_id !== conversationId) return;
      if (msg.streaming && !msg.done) {
        setStreaming(true);
        setStreamBuffer((prev) => prev + (msg.content || ""));
      } else if (msg.done) {
        setStreaming(false);
        setStreamBuffer((buf) => {
          const content = buf || msg.content || "";
          if (content) {
            setMessages((m) => [
              ...m,
              { role: "assistant", content, tools_used: msg.tools_used || [] },
            ]);
          }
          return "";
        });
      }
    });
  }, [addListener, conversationId]);

  useEffect(() => {
    if (!open || !connected) return;
    if (chatStartedRef.current && conversationId) return;
    const stored = loadStoredSession();
    sendMessage({
      type: "chat_start",
      operator_name: "default",
      ...(stored?.conversationId ? { conversation_id: stored.conversationId } : {}),
    });
  }, [open, connected, sendMessage, conversationId]);

  useEffect(() => {
    if (open) return;
    if (conversationId && !endSentRef.current) {
      sendMessage({ type: "chat_end", conversation_id: conversationId });
      endSentRef.current = true;
    }
    chatStartedRef.current = false;
  }, [open, conversationId, sendMessage]);

  const sendChat = useCallback(
    (content) => {
      if (!content.trim() || !conversationId) return;
      setMessages((m) => [...m, { role: "user", content }]);
      setStreaming(true);
      setStreamBuffer("");
      sendMessage({
        type: "chat_message",
        conversation_id: conversationId,
        operator_name: "default",
        content,
        dashboard_context: dashboardContext?.getContext?.() || {},
      });
    },
    [conversationId, sendMessage, dashboardContext]
  );

  const prefillChat = useCallback((text) => {
    setPrefill(text);
    setOpen(true);
  }, []);

  useEffect(() => {
    if (prefill && open && conversationId) {
      sendChat(prefill);
      setPrefill("");
    }
  }, [prefill, open, conversationId, sendChat]);

  const value = useMemo(
    () => ({
      open,
      setOpen,
      messages,
      streaming,
      streamBuffer,
      conversationId,
      resumed,
      sendChat,
      prefillChat,
    }),
    [open, messages, streaming, streamBuffer, conversationId, resumed, sendChat, prefillChat]
  );

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
}

export function useChat() {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error("useChat must be used within ChatProvider");
  return ctx;
}
