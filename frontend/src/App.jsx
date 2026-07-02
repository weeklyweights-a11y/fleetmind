import { useCallback, useEffect, useState } from "react";
import { useWebSocket } from "./hooks/useWebSocket.js";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export default function App() {
  const [health, setHealth] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [uploadResult, setUploadResult] = useState(null);
  const [error, setError] = useState(null);
  const { connected, lastMessage, sendMessage } = useWebSocket();

  const fetchHealth = useCallback(async () => {
    const res = await fetch(`${API_URL}/api/health`);
    setHealth(await res.json());
  }, []);

  const fetchDocuments = useCallback(async () => {
    const res = await fetch(`${API_URL}/api/documents?limit=10`);
    if (res.ok) {
      const data = await res.json();
      setDocuments(data.items || []);
    }
  }, []);

  useEffect(() => {
    fetchHealth();
    fetchDocuments();
  }, [fetchHealth, fetchDocuments]);

  useEffect(() => {
    if (connected) {
      sendMessage({ type: "subscribe", topics: ["document_status"] });
      sendMessage({ type: "ping" });
    }
  }, [connected, sendMessage]);

  const handleUpload = async (event) => {
    event.preventDefault();
    setError(null);
    setUploadResult(null);
    const file = event.target.files?.[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch(`${API_URL}/api/documents/upload`, {
        method: "POST",
        body: formData,
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.message || "Upload failed");
        return;
      }
      setUploadResult(data);
      fetchDocuments();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="max-w-3xl mx-auto p-8 space-y-8">
      <header>
        <h1 className="text-3xl font-bold">FleetMind Phase 1</h1>
        <p className="text-slate-400 mt-2">Foundation health, upload, and WebSocket test</p>
      </header>

      <section className="rounded-lg border border-slate-800 p-4">
        <h2 className="text-lg font-semibold mb-3">Health</h2>
        {health ? (
          <ul className="space-y-1 text-sm">
            <li>Postgres: <span className={health.postgres === "connected" ? "text-green-400" : "text-red-400"}>{health.postgres}</span></li>
            <li>Redis: <span className={health.redis === "connected" ? "text-green-400" : "text-red-400"}>{health.redis}</span></li>
            <li>Neo4j: <span className={health.neo4j === "connected" ? "text-green-400" : "text-red-400"}>{health.neo4j}</span></li>
          </ul>
        ) : (
          <p className="text-slate-400">Loading...</p>
        )}
      </section>

      <section className="rounded-lg border border-slate-800 p-4">
        <h2 className="text-lg font-semibold mb-3">WebSocket</h2>
        <p className="text-sm">
          Status:{" "}
          <span className={connected ? "text-green-400" : "text-yellow-400"}>
            {connected ? "connected" : "connecting..."}
          </span>
        </p>
        {lastMessage && (
          <pre className="mt-2 text-xs bg-slate-900 p-2 rounded overflow-auto">{JSON.stringify(lastMessage, null, 2)}</pre>
        )}
      </section>

      <section className="rounded-lg border border-slate-800 p-4">
        <h2 className="text-lg font-semibold mb-3">Upload PDF</h2>
        <input type="file" accept="application/pdf" onChange={handleUpload} className="text-sm" />
        {uploadResult && (
          <p className="mt-2 text-green-400 text-sm">
            Uploaded document_id: {uploadResult.document_id} ({uploadResult.status})
          </p>
        )}
        {error && <p className="mt-2 text-red-400 text-sm">{error}</p>}
      </section>

      <section className="rounded-lg border border-slate-800 p-4">
        <h2 className="text-lg font-semibold mb-3">Recent Documents</h2>
        {documents.length === 0 ? (
          <p className="text-slate-400 text-sm">No documents yet</p>
        ) : (
          <ul className="text-sm space-y-2">
            {documents.map((doc) => (
              <li key={doc.id} className="border-b border-slate-800 pb-2">
                <div>{doc.original_filename}</div>
                <div className="text-slate-400">{doc.id} — {doc.processing_status}</div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
