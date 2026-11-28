"use client";
import { useCallback, useEffect, useRef, useState } from "react";

export type PollOptions = {
  /** Nonaktifkan polling bila syarat belum terpenuhi (misalnya belum ada map_version_id). */
  enabled?: boolean;
  /** Kosongkan data lama saat deps berubah (misalnya pindah ID pekerjaan). */
  resetOnDepsChange?: boolean;
};

/** Muat data sekarang lalu tiap `ms` milidetik tanpa permintaan tumpang tindih. Berhenti saat komponen dilepas. */
export function usePoll<T>(
  load: () => Promise<T>,
  ms: number,
  deps: unknown[] = [],
  options?: PollOptions,
) {
  const enabled = options?.enabled ?? true;
  const resetOnDepsChange = options?.resetOnDepsChange ?? false;
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<number | null>(null);
  const [loading, setLoading] = useState<boolean>(enabled);
  const loadRef = useRef(load);
  loadRef.current = load;
  const inFlightRef = useRef(false);
  const refreshQueuedRef = useRef(false);
  const aliveRef = useRef(true);
  const genRef = useRef(0);

  const runTick = useCallback(function tick(gen: number) {
    if (!aliveRef.current || gen !== genRef.current || inFlightRef.current) return;
    inFlightRef.current = true;
    loadRef
      .current()
      .then((d) => {
        if (!aliveRef.current || gen !== genRef.current) return;
        setData(d);
        setError(null);
        setLastUpdatedAt(Date.now());
        setLoading(false);
      })
      .catch((e: Error) => {
        if (!aliveRef.current || gen !== genRef.current) return;
        setError(e.message);
        setLoading(false);
      })
      .finally(() => {
        if (!aliveRef.current || gen !== genRef.current) return;
        inFlightRef.current = false;
        if (refreshQueuedRef.current) {
          refreshQueuedRef.current = false;
          tick(gen);
        }
      });
  }, []);

  const refresh = useCallback(() => {
    if (!enabled) return;
    if (inFlightRef.current) {
      refreshQueuedRef.current = true;
      return;
    }
    runTick(genRef.current);
  }, [enabled, runTick]);

  useEffect(() => {
    aliveRef.current = true;
    const gen = ++genRef.current;
    inFlightRef.current = false;
    refreshQueuedRef.current = false;

    if (!enabled) {
      if (resetOnDepsChange) {
        setData(null);
        setError(null);
        setLastUpdatedAt(null);
      }
      setLoading(false);
      return () => {
        aliveRef.current = false;
      };
    }

    if (resetOnDepsChange) {
      setData(null);
      setError(null);
      setLastUpdatedAt(null);
    }
    setLoading(true);

    runTick(gen);
    const timer = setInterval(() => runTick(gen), ms);
    return () => {
      aliveRef.current = false;
      clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, ms, resetOnDepsChange, runTick, ...deps]);

  return { data, error, lastUpdatedAt, loading, refresh };
}

type Shared = {
  subs: Set<() => void>;
  data: unknown;
  error: string | null;
  lastUpdatedAt: number | null;
  inFlight: boolean;
  timer?: ReturnType<typeof setInterval>;
};
const shared = new Map<unknown, Shared>();

/** Seperti usePoll, tapi semua pemanggil dengan fungsi `load` yang sama berbagi satu putaran. Pakai `ms` yang sama di semua tempat. */
export function useSharedPoll<T>(load: () => Promise<T>, ms: number) {
  const [, rerender] = useState(0);
  useEffect(() => {
    let e = shared.get(load);
    if (!e) {
      const entry: Shared = {
        subs: new Set(),
        data: null,
        error: null,
        lastUpdatedAt: null,
        inFlight: false,
      };
      const tick = () => {
        if (entry.inFlight) return;
        entry.inFlight = true;
        load()
          .then((d) => {
            entry.data = d;
            entry.error = null;
            entry.lastUpdatedAt = Date.now();
          })
          .catch((x: Error) => {
            entry.error = x.message;
          })
          .finally(() => {
            entry.inFlight = false;
            entry.subs.forEach((f) => f());
          });
      };
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
  return {
    data: (e?.data ?? null) as T | null,
    error: e?.error ?? null,
    lastUpdatedAt: e?.lastUpdatedAt ?? null,
  };
}
