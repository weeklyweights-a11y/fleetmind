import { statusBadgeClass } from "../../utils/format.js";

export function Badge({ children, status }) {
  return (
    <span className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${statusBadgeClass(status)}`}>
      {children || status}
    </span>
  );
}
