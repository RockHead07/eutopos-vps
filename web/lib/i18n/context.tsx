"use client";

import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { en, type TranslationKey } from "./en";
import { id } from "./id";
import { formatDate } from "@/lib/api";

export type Locale = "id" | "en";

export const LOCALES: { id: Locale; label: string }[] = [
  { id: "id", label: "ID" },
  { id: "en", label: "EN" },
];

const STORAGE_KEY = "eutopos-locale";

const dictionaries: Record<Locale, Record<TranslationKey, string>> = {
  id,
  en,
};

interface LocaleContextValue {
  locale: Locale;
  setLocale: (next: Locale) => void;
  t: (key: TranslationKey, vars?: Record<string, string | number>) => string;
}

const LocaleContext = createContext<LocaleContextValue>({
  locale: "id",
  setLocale: () => {},
  t: (key, vars) => interpolate(id[key] ?? en[key] ?? key, vars),
});

function interpolate(template: string, vars?: Record<string, string | number>): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (match, k) => {
    return k in vars ? String(vars[k]) : match;
  });
}

export function LocaleProvider({ children }: { children: React.ReactNode }) {
  // Always default to "id" so static export and initial client hydration match cleanly.
  const [locale, setLocaleState] = useState<Locale>("id");

  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored === "en" || stored === "id") {
        setLocaleState(stored);
        document.documentElement.lang = stored;
      } else {
        document.documentElement.lang = "id";
      }
    } catch {
      document.documentElement.lang = "id";
    }
  }, []);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {}
    document.documentElement.lang = next;
  }, []);

  const t = useCallback(
    (key: TranslationKey, vars?: Record<string, string | number>) => {
      const dict = dictionaries[locale] ?? dictionaries.id;
      const str = dict[key] ?? dictionaries.en[key] ?? key;
      return interpolate(str, vars);
    },
    [locale],
  );

  const value = useMemo(
    () => ({
      locale,
      setLocale,
      t,
    }),
    [locale, setLocale, t],
  );

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale() {
  const ctx = useContext(LocaleContext);
  return { locale: ctx.locale, setLocale: ctx.setLocale };
}

export function useT() {
  const ctx = useContext(LocaleContext);
  return ctx.t;
}

export function useFormatDate() {
  const { locale } = useLocale();
  return useCallback(
    (iso: string | null | undefined) => formatDate(iso, locale),
    [locale],
  );
}

export type { TranslationKey };
