const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export async function apiGet(path, params = {}) {
  const url = new URL(`${API_URL}${path}`);
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, v);
  });
  const res = await fetch(url);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.message || `Request failed: ${res.status}`);
  }
  return res.json();
}

export async function apiPost(path, body) {
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.message || `Request failed: ${res.status}`);
  }
  return res.json();
}

export async function apiUpload(path, formData) {
  const res = await fetch(`${API_URL}${path}`, { method: "POST", body: formData });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.message || `Upload failed: ${res.status}`);
  }
  return res.json();
}

export function fileUrl(documentId) {
  return `${API_URL}/api/documents/${documentId}/file`;
}

export { API_URL };
