import { useState } from "react";
import { useNavigate } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import { useChat } from "../../context/ChatContext.jsx";

function MarkdownLink({ href, children }) {
  const navigate = useNavigate();
  if (href && href.startsWith("/")) {
    return (
      <a
        href={href}
        className="text-blue-400 underline"
        onClick={(e) => {
          e.preventDefault();
          navigate(href);
        }}
      >
        {children}
      </a>
    );
  }
  return (
    <a href={href} className="text-blue-400 underline" target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  );
}

export function ChatSidebar({ contextChips = [] }) {
  const { open, setOpen, messages, streaming, streamBuffer, sendChat, conversationId } = useChat();
  const [input, setInput] = useState("");
  const [expandedSources, setExpandedSources] = useState({});

  if (!open) return null;

  const handleSend = () => {
    sendChat(input);
    setInput("");
  };

  const handleKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const mdComponents = { a: MarkdownLink };

  return (
    <aside className="fixed md:static right-0 top-14 bottom-0 w-full md:w-[400px] border-l border-slate-800 bg-slate-900 flex flex-col z-30 chat-fullscreen md:chat-fullscreen-none">
      <div className="p-3 border-b border-slate-800 flex justify-between items-center">
        <span className="font-medium text-sm">Fleet Assistant</span>
        <button type="button" onClick={() => setOpen(false)} className="text-slate-400 text-sm">
          Close
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {messages.map((m, i) => (
          <div
            key={i}
            className={`text-sm rounded p-2 max-w-[95%] ${
              m.role === "user" ? "bg-blue-900/30 ml-auto text-right" : "bg-slate-800 mr-auto text-left"
            }`}
          >
            <ReactMarkdown components={mdComponents}>{m.content}</ReactMarkdown>
            {m.tools_used?.length > 0 && (
              <div className="mt-2 text-left">
                <button
                  type="button"
                  className="text-xs text-slate-400 underline"
                  onClick={() => setExpandedSources((s) => ({ ...s, [i]: !s[i] }))}
                >
                  Sources ({m.tools_used.length})
                </button>
                {expandedSources[i] && (
                  <ul className="mt-1 text-xs text-slate-500 space-y-1">
                    {m.tools_used.map((t, j) => (
                      <li key={j}>
                        {t.function}: {t.result_summary || t.status}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>
        ))}
        {streaming && (
          <div className="text-sm text-slate-400 mr-auto text-left">
            {streamBuffer || <span className="animate-pulse">Typing…</span>}
          </div>
        )}
      </div>
      <div className="p-3 border-t border-slate-800">
        {contextChips.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-1">
            {contextChips.map((chip) => (
              <button
                key={chip}
                type="button"
                disabled={!conversationId}
                onClick={() => sendChat(chip)}
                className="text-xs px-2 py-1 rounded bg-slate-800 text-slate-300 hover:bg-slate-700 disabled:opacity-50"
              >
                {chip}
              </button>
            ))}
          </div>
        )}
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKey}
          rows={2}
          placeholder="Ask about your fleet…"
          className="w-full bg-slate-800 rounded p-2 text-sm resize-none"
        />
        <button
          type="button"
          onClick={handleSend}
          disabled={!conversationId}
          className="mt-2 w-full py-2 bg-blue-600 hover:bg-blue-500 rounded text-sm disabled:opacity-50"
        >
          Send
        </button>
      </div>
    </aside>
  );
}
