import { useCallback, useEffect, useState } from "react";
import { apiUpload } from "../../api/client.js";
import { useProcessingQueue } from "../../context/ProcessingQueueContext.jsx";

export function UploadZone({ open, onClose }) {
  const { addUpload } = useProcessingQueue();
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState([]);

  const uploadFiles = useCallback(
    async (files) => {
      const pdfs = [...files].filter((f) => f.type === "application/pdf" || f.name.endsWith(".pdf"));
      if (!pdfs.length) return;
      setUploading(true);
      setProgress(pdfs.map((f) => ({ name: f.name, status: "pending" })));

      const form = new FormData();
      pdfs.forEach((file) => form.append("files", file));

      try {
        setProgress((p) => p.map((x) => ({ ...x, status: "uploading" })));
        const result = await apiUpload("/api/documents/upload/batch", form);
        const ids = result.document_ids || [];
        const errorByName = Object.fromEntries(
          (result.errors || []).map((e) => [e.filename, e.message])
        );
        pdfs.forEach((file, i) => {
          const errMsg = errorByName[file.name];
          if (errMsg) {
            setProgress((p) =>
              p.map((x, j) => (j === i ? { ...x, status: "error", error: errMsg } : x))
            );
          } else {
            const docId = ids[i];
            if (docId) {
              addUpload({ document_id: docId, filename: file.name, status: "queued" });
            }
            setProgress((p) => p.map((x, j) => (j === i ? { ...x, status: "done" } : x)));
          }
        });
      } catch (err) {
        setProgress((p) => p.map((x) => ({ ...x, status: "error", error: err.message })));
      }

      setUploading(false);
      setTimeout(onClose, 1500);
    },
    [addUpload, onClose]
  );

  useEffect(() => {
    if (!open) return undefined;
    const onDrag = (e) => {
      e.preventDefault();
      e.stopPropagation();
    };
    const onDrop = (e) => {
      e.preventDefault();
      if (e.dataTransfer?.files?.length) uploadFiles(e.dataTransfer.files);
    };
    window.addEventListener("dragenter", onDrag);
    window.addEventListener("dragover", onDrag);
    window.addEventListener("drop", onDrop);
    return () => {
      window.removeEventListener("dragenter", onDrag);
      window.removeEventListener("dragover", onDrag);
      window.removeEventListener("drop", onDrop);
    };
  }, [open, uploadFiles]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/90 flex items-center justify-center p-4">
      <div className="max-w-lg w-full rounded-xl border-2 border-dashed border-blue-500/50 bg-slate-900 p-8 text-center">
        <h2 className="text-xl font-semibold mb-2">Drop PDF files to upload</h2>
        <p className="text-sm text-slate-400 mb-4">PDF only. Images accepted in UI but not processed yet.</p>
        <input
          type="file"
          accept="application/pdf"
          multiple
          disabled={uploading}
          onChange={(e) => e.target.files && uploadFiles(e.target.files)}
          className="text-sm"
        />
        {progress.length > 0 && (
          <ul className="mt-4 text-left text-sm space-y-1">
            {progress.map((p) => (
              <li key={p.name} className="text-slate-300">
                {p.name}: {p.status}
                {p.error && <span className="text-red-400"> — {p.error}</span>}
              </li>
            ))}
          </ul>
        )}
        <button type="button" onClick={onClose} className="mt-4 text-sm text-slate-400 hover:text-white">
          Close
        </button>
      </div>
    </div>
  );
}
