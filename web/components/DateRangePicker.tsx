"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { DateRange } from "react-day-picker";
import { id as idLocale, enUS as enUSLocale } from "date-fns/locale";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Icon } from "@/lib/Icon";
import { useLocale, useT } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export interface DateRangeValue {
  from?: string;
  to?: string;
}

interface DateRangePickerProps {
  value: DateRangeValue;
  onChange: (value: DateRangeValue) => void;
  className?: string;
}

function parseLocalYMD(s: string): Date {
  const [y, m, d] = s.split("-").map(Number);
  return new Date(y, m - 1, d, 0, 0, 0, 0);
}

function toLocalYMD(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function formatRangeLabel(from: string | undefined, to: string | undefined, locale: string, allTimeText: string): string {
  if (!from && !to) return allTimeText;
  const loc = locale === "id" ? "id-ID" : "en-US";
  if (from && (!to || from === to)) {
    const d = parseLocalYMD(from);
    return d.toLocaleDateString(loc, { month: "short", day: "numeric", year: "numeric" });
  }
  if (!from && to) {
    const d = parseLocalYMD(to);
    return d.toLocaleDateString(loc, { month: "short", day: "numeric", year: "numeric" });
  }
  if (from && to) {
    const dFrom = parseLocalYMD(from);
    const dTo = parseLocalYMD(to);
    const yFrom = dFrom.getFullYear();
    const yTo = dTo.getFullYear();
    const mFrom = dFrom.toLocaleDateString(loc, { month: "short" });
    const mTo = dTo.toLocaleDateString(loc, { month: "short" });
    const dayFrom = dFrom.getDate();
    const dayTo = dTo.getDate();
    if (yFrom === yTo) {
      if (mFrom === mTo) {
        return `${mFrom} ${dayFrom} – ${dayTo}, ${yTo}`;
      }
      return `${mFrom} ${dayFrom} – ${mTo} ${dayTo}, ${yTo}`;
    }
    return `${mFrom} ${dayFrom}, ${yFrom} – ${mTo} ${dayTo}, ${yTo}`;
  }
  return allTimeText;
}

export function DateRangePicker({ value, onChange, className }: DateRangePickerProps) {
  const [open, setOpen] = useState(false);
  const today = useMemo(() => new Date(), []);
  const { locale } = useLocale();
  const t = useT();

  // Internal DateRange object for DayPicker
  const [selectedRange, setSelectedRange] = useState<DateRange | undefined>(() => {
    if (!value.from) return undefined;
    const from = parseLocalYMD(value.from);
    const to = value.to ? parseLocalYMD(value.to) : from;
    return { from, to };
  });

  // Sync external value changes (e.g. Reset button)
  useEffect(() => {
    if (!value.from && !value.to) {
      setSelectedRange(undefined);
    } else if (value.from) {
      const from = parseLocalYMD(value.from);
      const to = value.to ? parseLocalYMD(value.to) : from;
      setSelectedRange({ from, to });
    }
  }, [value.from, value.to]);

  // Press-and-drag state refs
  const isDraggingRef = useRef(false);
  const anchorDayRef = useRef<string | null>(null);
  const hasDraggedRef = useRef(false);
  const dragEndedAtRef = useRef<number>(0);

  const getDayFromPoint = (x: number, y: number): string | null => {
    const el = document.elementFromPoint(x, y);
    if (!el) return null;
    const btn = el.closest<HTMLButtonElement>("button[data-day]");
    if (btn && btn.dataset.day && !btn.disabled) {
      return btn.dataset.day;
    }
    return null;
  };

  const updateRangeFromAnchorAndCurrent = useCallback(
    (currentDay: string) => {
      const anchor = anchorDayRef.current;
      if (!anchor) return;
      const d1 = parseLocalYMD(anchor);
      const d2 = parseLocalYMD(currentDay);
      const from = d1 <= d2 ? d1 : d2;
      const to = d1 <= d2 ? d2 : d1;
      const newRange = { from, to };
      setSelectedRange(newRange);
      onChange({ from: toLocalYMD(from), to: toLocalYMD(to) });
    },
    [onChange]
  );

  const handlePointerDown = (e: React.PointerEvent) => {
    if (e.button !== 0) return;
    const day = getDayFromPoint(e.clientX, e.clientY);
    if (day) {
      isDraggingRef.current = true;
      anchorDayRef.current = day;
      hasDraggedRef.current = false;
      try {
        (e.target as HTMLElement).setPointerCapture(e.pointerId);
      } catch {}
    }
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    if (!isDraggingRef.current || !anchorDayRef.current) return;
    const day = getDayFromPoint(e.clientX, e.clientY);
    if (day && day !== anchorDayRef.current) {
      hasDraggedRef.current = true;
      updateRangeFromAnchorAndCurrent(day);
    }
  };

  const handlePointerUp = (e: React.PointerEvent) => {
    if (isDraggingRef.current) {
      isDraggingRef.current = false;
      try {
        (e.target as HTMLElement).releasePointerCapture(e.pointerId);
      } catch {}
      if (hasDraggedRef.current) {
        dragEndedAtRef.current = Date.now();
      }
      anchorDayRef.current = null;
      hasDraggedRef.current = false;
    }
  };

  const handlePointerCancel = () => {
    isDraggingRef.current = false;
    anchorDayRef.current = null;
    hasDraggedRef.current = false;
  };

  const handleClickCapture = (e: React.MouseEvent) => {
    if (Date.now() - dragEndedAtRef.current < 200) {
      e.preventDefault();
      e.stopPropagation();
    }
  };

  const handleDayPickerSelect = (range: DateRange | undefined) => {
    if (Date.now() - dragEndedAtRef.current < 200) return;
    if (!range) {
      setSelectedRange(undefined);
      onChange({ from: undefined, to: undefined });
      return;
    }

    if (range.from && !range.to) {
      const fromStr = toLocalYMD(range.from);
      setSelectedRange({ from: range.from, to: range.from });
      onChange({ from: fromStr, to: fromStr });
    } else if (range.from && range.to) {
      const fromStr = toLocalYMD(range.from);
      const toStr = toLocalYMD(range.to);
      setSelectedRange(range);
      onChange({ from: fromStr, to: toStr });
    }
  };

  const handleClear = () => {
    setSelectedRange(undefined);
    onChange({ from: undefined, to: undefined });
  };

  const label = formatRangeLabel(value.from, value.to, locale, t("date.allTime"));

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          className={cn(
            "h-9 rounded-lg border-line bg-card px-3 text-xs max-[959px]:text-base text-foreground font-normal hover:bg-muted/50 flex items-center justify-between gap-2 shadow-xs cursor-pointer",
            className
          )}
          title={label}
          aria-label={t("date.selectRangeAria")}
        >
          <span className="truncate">{label}</span>
          <Icon name="calendar" />
        </Button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        collisionPadding={16}
        className="mobile-popover w-auto p-3 bg-card border-line rounded-2xl shadow-lg"
      >
        <div
          onClickCapture={handleClickCapture}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerCancel}
        >
          <Calendar
            mode="range"
            locale={locale === "id" ? idLocale : enUSLocale}
            selected={selectedRange}
            onSelect={handleDayPickerSelect}
            disabled={{ after: today }}
            showOutsideDays={true}
            defaultMonth={selectedRange?.from || today}
          />
        </div>

        <div className="flex items-center justify-between pt-3 mt-1 border-t border-line/60">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={handleClear}
            className="text-xs text-muted-foreground hover:text-foreground h-8 px-2.5 cursor-pointer"
          >
            {t("date.clear")}
          </Button>
          <Button
            type="button"
            size="sm"
            onClick={() => setOpen(false)}
            className="text-xs bg-forest hover:bg-forest-hover text-white h-8 px-3.5 rounded-lg cursor-pointer font-medium"
          >
            {t("date.done")}
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
