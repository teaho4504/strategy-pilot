import { useEffect, useState } from "react";

export function useDeferredPageReady(delayMs = 350) {
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setReady(false);
    const id = window.setTimeout(() => setReady(true), delayMs);
    return () => window.clearTimeout(id);
  }, [delayMs]);

  return ready;
}
