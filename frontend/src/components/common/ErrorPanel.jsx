export function ErrorPanel({ message, onRetry }) {
  return (
    <div className="rounded-lg border border-red-900/50 bg-red-950/30 p-4">
      <p className="text-red-300 text-sm">{message || "Something went wrong."}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-2 text-xs text-red-200 underline hover:text-white"
        >
          Retry
        </button>
      )}
    </div>
  );
}
