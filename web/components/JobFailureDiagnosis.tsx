"use client";

import { useState } from "react";
import { Icon } from "@/lib/Icon";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface JobFailureDiagnosisProps {
  error: string;
  stage?: string | null;
  className?: string;
}

export function JobFailureDiagnosis({
  error,
  stage,
  className,
}: JobFailureDiagnosisProps) {
  const [copied, setCopied] = useState(false);
  const [isOpen, setIsOpen] = useState(false);

  // Split the error message: the first line is the primary exception string from worker,
  // subsequent lines contain the log tail from worker log.txt.
  const lines = error.split("\n");
  const summary = lines[0].trim();
  const logTail = lines.slice(1).join("\n").trim();

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(error);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard write failed or blocked
    }
  };

  return (
    <div className={cn("rounded-lg border border-bad-fg/30 bg-bad-bg/40 p-4 text-xs", className)}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2.5">
          <div className="mt-0.5 rounded-full bg-bad-fg/10 p-1 text-bad-fg">
            <Icon name="error-map" />
          </div>
          <div className="flex flex-col gap-1">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-bad-fg text-sm">Failure Diagnosis</span>
              {stage && (
                <span className="rounded bg-bad-fg/15 px-1.5 py-0.5 text-[10px] font-mono text-bad-fg">
                  Stage: {stage}
                </span>
              )}
            </div>
            <p className="font-medium text-foreground leading-relaxed">
              {summary || "An unexpected error occurred during reconstruction."}
            </p>
          </div>
        </div>

        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={handleCopy}
          className="h-7 text-xs border-bad-fg/30 text-bad-fg hover:bg-bad-fg/10 shrink-0 cursor-pointer"
        >
          {copied ? "Copied" : "Copy error"}
        </Button>
      </div>

      {logTail && (
        <div className="mt-3 border-t border-bad-fg/20 pt-3">
          <button
            type="button"
            onClick={() => setIsOpen(!isOpen)}
            className="flex items-center gap-1.5 font-medium text-bad-fg hover:underline cursor-pointer text-xs"
          >
            <span>{isOpen ? "▼ Hide worker diagnostic logs" : "▶ Show worker diagnostic logs (tail)"}</span>
          </button>

          {isOpen && (
            <div className="mt-2 flex flex-col gap-1.5">
              <div className="text-[11px] text-muted-foreground">
                Last execution output from worker process:
              </div>
              <pre className="max-h-64 overflow-x-auto overflow-y-auto rounded bg-card/80 p-3 font-mono text-[11px] leading-snug text-foreground/90 border border-line">
                {logTail}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
