import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { useChat } from "../../context/ChatContext.jsx";

export function ChatSidebar({ contextChips = [] }) {
  const { open, setOpen, messages, streaming, streamBuffer, sendChat } = useChat();
  const [input, setInput] = useState("");

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

  return (
      <aside className={`fixed md:static right-0 top-14 bottom-0 w-full md:w-[400px] border-l border-slate-800 bg-slate-900 flex flex-col z-30 chat-fullscreen md:chat-fullscreen-none`}>
      <div className="p-3 border-b border-slate-800 flex justify-between items-center">
        <span className="font-medium text-sm">Fleet Assistant</span>
        <button type="button" onClick={() => setOpen(false)} className="text-slate-400 text-sm">
          Close
        </button>
      </div>
      {contextChips.length > 0 && (
        <div className="p-2 flex flex-wrap gap-1 border-b border-slate-800">
          {contextChips.map((chip) => (
            <button
              key={chip}
              type="button"
              onClick={() => sendChat(chip)}
              className="text-xs px-2 py-1 rounded bg-slate-800 text-slate-300 hover:bg-slate-700"
            >
              {chip}
            </button>
          ))}
        </div>
      )}
      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {messages.map((m, i) => (
          <div
            key={i}
            className={`text-sm rounded p-2 ${
              m.role === "user" ? "bg-blue-900/30 ml-4" : "bg-slate-800 mr-4"
            }`}
          >
            <ReactMarkdown
              components={{
                a: ({ href, children }) => (
                  <a href={href} className="text-blue-400 underline">
                    {children}
                  </a>
                ),
              }}
            >
              {m.content}
            </ReactMarkdown>
          </div>
        ))}
        {streaming && (
          <div className="text-sm text-slate-400 mr-4">
            {streamBuffer || <span className="animate-pulse">Typing…</span>}
          </div>
        )}
      </div>
      <div className="p-3 border-t border-slate-800">
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
          className="mt-2 w-full py-2 bg-blue-600 hover:bg-blue-500 rounded text-sm"
        >
          Send
        </button>
      </div>
    </aside>
  );
}
