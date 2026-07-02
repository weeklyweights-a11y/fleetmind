import { ConnectionIndicator } from "./ConnectionIndicator.jsx";

export function Header({
  onMenuClick,
  onUploadClick,
  onChatToggle,
  notificationCount = 0,
  chatOpen,
}) {
  return (
    <header className="h-14 border-b border-slate-800 bg-slate-950/80 backdrop-blur flex items-center justify-between px-4 gap-4">
      <div className="flex items-center gap-3">
        <button
          type="button"
          className="md:hidden p-2 text-slate-400 hover:text-white"
          onClick={onMenuClick}
          aria-label="Open menu"
        >
          ☰
        </button>
        <ConnectionIndicator />
      </div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onUploadClick}
          className="px-3 py-1.5 text-sm bg-blue-600 hover:bg-blue-500 rounded"
        >
          Upload
        </button>
        {notificationCount > 0 && (
          <span className="px-2 py-0.5 text-xs bg-amber-600 rounded-full">{notificationCount}</span>
        )}
        <button
          type="button"
          onClick={onChatToggle}
          className={`px-3 py-1.5 text-sm rounded border ${
            chatOpen ? "border-blue-500 text-blue-300" : "border-slate-700 text-slate-300 hover:border-slate-500"
          }`}
        >
          Chat
        </button>
      </div>
    </header>
  );
}
