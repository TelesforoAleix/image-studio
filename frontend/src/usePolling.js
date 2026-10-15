import { useEffect, useRef, useState } from "react";

// Page/revision changes load once. Only active generations keep the timer alive.
export function usePolling(load, active, identity, revision) {
  const latest = useRef(load);
  latest.current = load;
  const [error, setError] = useState("");
  const inFlight = useRef(false);
  useEffect(() => {
    let cancelled = false;
    inFlight.current = false;
    const refresh = async () => {
      if (inFlight.current) return;
      inFlight.current = true;
      try {
        await latest.current(() => !cancelled);
        if (!cancelled) setError("");
      } catch (e) {
        if (!cancelled) setError(e.message);
      } finally {
        if (!cancelled) inFlight.current = false;
      }
    };
    refresh();
    const timer = active ? setInterval(refresh, 3000) : null;
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [active, identity, revision]);
  return error;
}
