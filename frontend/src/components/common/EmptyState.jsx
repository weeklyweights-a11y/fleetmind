export function EmptyState({ title, message, action }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <p className="text-lg font-medium text-slate-300">{title}</p>
      {message && <p className="mt-2 text-sm text-slate-500 max-w-md">{message}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
