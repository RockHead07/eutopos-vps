"use client";

import { useEffect, useRef, useState } from "react";
import { Icon } from "@/lib/Icon";
import { cn } from "@/lib/utils";

interface SearchBarProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit?: () => void;
  variant: "hero" | "compact";
  shortcut?: boolean;
  placeholder?: string;
  className?: string;
  autoFocus?: boolean;
}

export function SearchBar({
  value,
  onChange,
  onSubmit,
  variant,
  shortcut = false,
  placeholder,
  className,
  autoFocus,
}: SearchBarProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isMac, setIsMac] = useState(false);

  useEffect(() => {
    setIsMac(/(Mac|iPhone|iPod|iPad)/i.test(navigator.userAgent || navigator.platform || ""));
  }, []);

  useEffect(() => {
    if (!shortcut) return;

    const handleGlobalKeyDown = (e: KeyboardEvent) => {
      const isModifier = e.ctrlKey || e.metaKey;
      if (isModifier && e.key === "/") {
        e.preventDefault();
        inputRef.current?.focus();
        return;
      }

      if (e.key === "/" && !e.ctrlKey && !e.metaKey && !e.altKey) {
        const activeEl = document.activeElement;
        const isInput =
          activeEl instanceof HTMLInputElement ||
          activeEl instanceof HTMLTextAreaElement ||
          activeEl instanceof HTMLSelectElement ||
          activeEl?.getAttribute("contenteditable") === "true" ||
          (activeEl as HTMLElement)?.isContentEditable;

        if (!isInput) {
          e.preventDefault();
          inputRef.current?.focus();
        }
      }
    };

    window.addEventListener("keydown", handleGlobalKeyDown);
    return () => {
      window.removeEventListener("keydown", handleGlobalKeyDown);
    };
  }, [shortcut]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Escape") {
      e.preventDefault();
      if (value) {
        onChange("");
      } else {
        inputRef.current?.blur();
      }
    } else if (e.key === "Enter" && onSubmit) {
      e.preventDefault();
      onSubmit();
    }
  };

  const defaultPlaceholder =
    variant === "hero" ? "Search jobs, areas or people..." : "Search...";

  const chips = (
    <div
      className="hidden sm:inline-flex items-center gap-1 shrink-0 select-none text-[11px] font-medium text-muted-foreground"
      aria-hidden="true"
    >
      <kbd className="inline-flex items-center justify-center min-w-5 h-5 px-1.5 rounded bg-muted/60 border border-line text-[11px] font-sans leading-none shadow-xs">
        {isMac ? "⌘" : "Ctrl"}
      </kbd>
      <span className="text-[10px] text-muted-foreground/60">+</span>
      <kbd className="inline-flex items-center justify-center min-w-5 h-5 px-1.5 rounded bg-muted/60 border border-line text-[11px] font-sans leading-none shadow-xs">
        /
      </kbd>
    </div>
  );

  const innerField = (
    <div
      className={cn(
        "relative flex items-center w-full bg-card border transition-colors focus-within:border-forest focus-within:ring-1 focus-within:ring-forest",
        variant === "hero"
          ? "h-12 rounded-2xl border-line/70 px-3.5 gap-2.5 shadow-[inset_0_1px_2px_rgba(0,0,0,0.03)]"
          : "h-9 rounded-lg border-line px-3 gap-2 shadow-[inset_0_1px_2px_rgba(0,0,0,0.03)]",
        variant === "compact" && className
      )}
    >
      <span className="shrink-0 flex items-center text-muted-foreground">
        <Icon name="search" />
      </span>
      <input
        ref={inputRef}
        type="search"
        role="searchbox"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder || defaultPlaceholder}
        aria-label="Search"
        aria-keyshortcuts="Control+/ Meta+/ /"
        autoFocus={autoFocus}
        className={cn(
          "w-full min-w-0 bg-transparent text-foreground placeholder:text-muted-foreground focus:outline-none [appearance:textfield] [&::-webkit-search-cancel-button]:hidden",
          variant === "hero" ? "text-xs sm:text-sm" : "text-xs"
        )}
      />
      {chips}
    </div>
  );

  if (variant === "hero") {
    return (
      <div
        role="search"
        className={cn(
          "w-full p-1 rounded-[28px] border border-line/80 bg-gradient-to-b from-mist/50 to-card/60 backdrop-blur-md shadow-xs shadow-[inset_0_1px_0_rgba(255,255,255,0.7)]",
          className
        )}
      >
        {innerField}
      </div>
    );
  }

  return (
    <div role="search" className="w-full">
      {innerField}
    </div>
  );
}
