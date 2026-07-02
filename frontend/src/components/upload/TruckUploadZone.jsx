import { useState } from "react";
import { UploadZone } from "./UploadZone.jsx";

export function TruckUploadZone({ truckUnit }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="mt-3 p-3 rounded border border-dashed border-slate-700 text-center">
      <p className="text-xs text-slate-500 mb-2">
        Drop files here to add documents to truck {truckUnit}
      </p>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="text-xs text-blue-400 hover:text-blue-300"
      >
        Upload PDF
      </button>
      <UploadZone open={open} onClose={() => setOpen(false)} />
    </div>
  );
}
