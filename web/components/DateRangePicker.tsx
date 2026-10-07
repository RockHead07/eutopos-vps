"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { DateRange } from "react-day-picker";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Icon } from "@/lib/Icon";
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

function formatRangeLabel(from?: string, to?: string): string {
  if (!from && !to) return "All time";
  if (from && (!to || from === to)) {
    const d = parseLocalYMD(from);
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  }
  if (!from && to) {
    const d = parseLocalYMD(to);
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  }
  if (from && to) {
    const dFrom = parseLocalYMD(from);
    const dTo = parseLocalYMD(to);
    const yFrom = dFrom.getFullYear();
    const yTo = dTo.getFullYear();
    const mFrom = dFrom.toLocaleDateString("en-US", { month: "short" });
    const mTo = dTo.toLocaleDateString("en-US", { month: "short" });
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
  return "All time";
}

export function DateRangePicker({ value, onChange, className }: DateRangePickerProps) {
  const [open, setOpen] = useState(false);
  const today = useMemo(() => new Date(), []);
  const todayStr = useMemo(() => toLocalYMD(today), [today]);

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
    const dayEl = el.closest("[data-day]");
    if (!dayEl) return null;
    if (
      dayEl.getAttribute("data-disabled") === "true" ||
      dayEl.getAttribute("aria-disabled") === "true"
    ) {
      return null;
    }
    const dayStr = dayEl.getAttribute("data-day");
    if (!dayStr || dayStr > todayStr) return null;
    return dayStr;
  };

  const endDrag = useCallback(() => {
    if (!isDraggingRef.current) return;
    if (hasDraggedRef.current) {
      dragEndedAtRef.current = performance.now();
    }
    isDraggingRef.current = false;
    anchorDayRef.current = null;
    hasDraggedRef.current = false;
    window.removeEventListener("pointerup", endDrag);
    window.removeEventListener("pointercancel", endDrag);
  }, []);

  useEffect(() => {
    if (!open) {
      endDrag();
    }
    return () => {
      window.removeEventListener("pointerup", endDrag);
      window.removeEventListener("pointercancel", endDrag);
    };
  }, [open, endDrag]);

  const handlePointerDown = (e: React.PointerEvent) => {
    dragEndedAtRef.current = 0;
    if (e.button !== 0) return;
    const day = getDayFromPoint(e.clientX, e.clientY);
    if (!day) return;

    anchorDayRef.current = day;
    isDraggingRef.current = true;
    hasDraggedRef.current = false;

    window.addEventListener("pointerup", endDrag);
    window.addEventListener("pointercancel", endDrag);
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    if (!isDraggingRef.current || !anchorDayRef.current) return;

    if (e.pointerType === "mouse" && e.buttons === 0) {
      endDrag();
      return;
    }

    const currentDay = getDayFromPoint(e.clientX, e.clientY);
    if (!currentDay) return;

    if (currentDay !== anchorDayRef.current) {
      hasDraggedRef.current = true;
      const anchor = anchorDayRef.current;
      const startStr = currentDay < anchor ? currentDay : anchor;
      const endStr = currentDay > anchor ? currentDay : anchor;

      const fromDate = parseLocalYMD(startStr);
      const toDate = parseLocalYMD(endStr);
      setSelectedRange({ from: fromDate, to: toDate });
      onChange({ from: startStr, to: endStr });
    }
  };

  const handlePointerUp = () => {
    endDrag();
  };

  const handlePointerCancel = () => {
    endDrag();
  };

  const handleClickCapture = (e: React.MouseEvent) => {
    if (dragEndedAtRef.current > 0) {
      const elapsed = performance.now() - dragEndedAtRef.current;
      dragEndedAtRef.current = 0;
      if (elapsed < 300) {
        e.preventDefault();
        e.stopPropagation();
      }
    }
  };

  const handleDayPickerSelect = (range: DateRange | undefined) => {
    setSelectedRange(range);
    if (!range?.from) {
      onChange({ from: undefined, to: undefined });
    } else {
      const fromStr = toLocalYMD(range.from);
      const toStr = range.to ? toLocalYMD(range.to) : fromStr;
      onChange({ from: fromStr, to: toStr });
    }
  };

  const handleClear = () => {
    setSelectedRange(undefined);
    onChange({ from: undefined, to: undefined });
  };

  const label = formatRangeLabel(value.from, value.to);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          className={cn(
            "h-9 rounded-lg border-line bg-card px-3 text-xs text-foreground font-normal hover:bg-muted/50 flex items-center justify-between gap-2 shadow-xs cursor-pointer",
            className
          )}
          aria-label="Select date range"
        >
          <span className="truncate">{label}</span>
          <Icon name="calendar" />
        </Button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        collisionPadding={16}
        className="w-auto p-3 bg-card border-line rounded-2xl shadow-lg max-w-[calc(100vw-2rem)]"
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
            Clear
          </Button>
          <Button
            type="button"
            size="sm"
            onClick={() => setOpen(false)}
            className="text-xs bg-forest hover:bg-forest-hover text-white h-8 px-3.5 rounded-lg cursor-pointer font-medium"
          >
            Done
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
