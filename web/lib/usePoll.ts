"use client";
import { useEffect, useState } from "react";

/** Muat data sekarang lalu tiap `ms` milidetik. Berhenti saat komponen dilepas. */
export function usePoll<T>(load: () => Promise<T>, ms: number, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    const tick = () =>
      load()
        .then((d) => alive && (setData(d), setError(null)))
        .catch((e: Error) => alive && setError(e.message));
    tick();
    const timer = setInterval(tick, ms);
    return () => {
      alive = false;
      clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return { data, error };
}
