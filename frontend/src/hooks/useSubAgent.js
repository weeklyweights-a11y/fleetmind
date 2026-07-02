import { useCallback, useEffect, useRef, useState } from "react";
import { useLiveUpdate } from "./useLiveUpdate.js";

export function useSubAgent(fetcher, { topic, applyDelta, deps } = {}) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const mountedRef = useRef(true);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const refetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetcherRef.current();
      if (mountedRef.current) setData(result);
    } catch (err) {
      if (mountedRef.current) setError(err.message || "Failed to load");
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    refetch();
    return () => {
      mountedRef.current = false;
    };
  }, deps ?? [refetch]);

  useLiveUpdate(topic, (msg) => {
    if (msg.delta?.refetch || msg.delta?.new_event) {
      refetch();
      return;
    }
    if (applyDelta && msg.delta) {
      setData((prev) => applyDelta(prev, msg.delta));
    }
  });

  return { data, loading, error, refetch, setData };
}
