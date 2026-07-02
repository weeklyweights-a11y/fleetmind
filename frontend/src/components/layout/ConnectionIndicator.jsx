import { useWebSocketContext } from "../../context/WebSocketContext.jsx";

export function ConnectionIndicator() {
  const { connectionState, nextRetryIn } = useWebSocketContext();

  const colors = {
    connected: "bg-emerald-500",
    connecting: "bg-amber-500 animate-pulse",
    reconnecting: "bg-amber-500 animate-pulse",
    disconnected: "bg-red-500",
  };

  const labels = {
    connected: "Connected",
    connecting: "Connecting…",
    reconnecting: `Reconnecting${nextRetryIn ? ` in ${nextRetryIn}s` : "…"}`,
    disconnected: "Disconnected",
  };

  return (
    <div className="flex items-center gap-2 text-xs text-slate-400">
      <span className={`w-2 h-2 rounded-full ${colors[connectionState] || colors.disconnected}`} />
      <span>{labels[connectionState] || connectionState}</span>
    </div>
  );
}
