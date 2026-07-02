import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { apiGet } from "../api/client.js";
import { useWebSocketContext } from "./WebSocketContext.jsx";

const IN_FLIGHT = "queued,parsing,extracting,normalizing,validating,correcting,saving,needs_review";

const ProcessingQueueContext = createContext(null);

export function ProcessingQueueProvider({ children }) {
  const [queue, setQueue] = useState([]);
  const [todayCount, setTodayCount] = useState(0);
  const { addListener } = useWebSocketContext();

  const hydrate = useCallback(async () => {
    try {
      const data = await apiGet("/api/documents", {
        processing_status_in: IN_FLIGHT,
        sort_by: "created_at",
        sort_order: "desc",
        limit: 50,
      });
      const items = (data.items || []).map((doc) => ({
        document_id: doc.id,
        filename: doc.original_filename,
        status: doc.processing_status,
        progress: { current_layer: 0, total_layers: 7 },
        details: { document_type: doc.document_type, truck_unit: doc.truck_unit },
      }));
      setQueue(items);
    } catch {
      /* ignore hydrate errors */
    }
  }, []);

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  useEffect(() => {
    return addListener((msg) => {
      if (msg.type !== "document_status") return;
      setQueue((prev) => {
        const idx = prev.findIndex((q) => q.document_id === msg.document_id);
        const entry = {
          document_id: msg.document_id,
          filename: msg.filename,
          status: msg.status,
          progress: msg.progress || { current_layer: 0, total_layers: 7 },
          details: msg.details || {},
          error_details: msg.error_details,
        };
        const terminal = ["complete", "failed", "needs_review"].includes(msg.status);
        if (idx >= 0) {
          if (terminal) {
            const next = [...prev];
            next[idx] = entry;
            return next;
          }
          const next = [...prev];
          next[idx] = entry;
          return next;
        }
        if (!terminal || msg.status === "queued") return [entry, ...prev];
        return prev;
      });
    });
  }, [addListener]);

  const addUpload = useCallback((doc) => {
    setTodayCount((c) => c + 1);
    setQueue((prev) => [
      {
        document_id: doc.document_id,
        filename: doc.filename || "upload.pdf",
        status: doc.status || "queued",
        progress: { current_layer: 0, total_layers: 7 },
        details: {},
      },
      ...prev,
    ]);
  }, []);

  const inFlightCount = useMemo(
    () => queue.filter((q) => !["complete", "failed"].includes(q.status)).length,
    [queue]
  );

  const value = useMemo(
    () => ({ queue, inFlightCount, todayCount, addUpload, hydrate }),
    [queue, inFlightCount, todayCount, addUpload, hydrate]
  );

  return (
    <ProcessingQueueContext.Provider value={value}>{children}</ProcessingQueueContext.Provider>
  );
}

export function useProcessingQueue() {
  const ctx = useContext(ProcessingQueueContext);
  if (!ctx) throw new Error("useProcessingQueue must be used within ProcessingQueueProvider");
  return ctx;
}
