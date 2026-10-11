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

type Shared = { subs: Set<() => void>; data: unknown; error: string | null; timer?: ReturnType<typeof setInterval> };
const shared = new Map<unknown, Shared>();

/** Seperti usePoll, tapi semua pemanggil dengan fungsi `load` yang sama berbagi satu putaran. Pakai `ms` yang sama di semua tempat. */
export function useSharedPoll<T>(load: () => Promise<T>, ms: number) {
  const [, rerender] = useState(0);
  useEffect(() => {
    let e = shared.get(load);
    if (!e) {
      const entry: Shared = { subs: new Set(), data: null, error: null };
      const tick = () =>
        load()
          .then((d) => ((entry.data = d), (entry.error = null)))
          .catch((x: Error) => (entry.error = x.message))
          .finally(() => entry.subs.forEach((f) => f()));
      tick();
      entry.timer = setInterval(tick, ms);
      shared.set(load, entry);
      e = entry;
    }
    const sub = () => rerender((n) => n + 1);
    e.subs.add(sub);
    return () => {
      e.subs.delete(sub);
      if (!e.subs.size) {
        clearInterval(e.timer);
        shared.delete(load);
      }
    };
  }, [load, ms]);
  const e = shared.get(load);
  return { data: (e?.data ?? null) as T | null, error: e?.error ?? null };
}
