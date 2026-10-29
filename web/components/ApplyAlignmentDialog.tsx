"use client";

import { useEffect, useRef, useState } from "react";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { useT } from "@/lib/i18n";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  lines: string[]; // ringkasan perubahan, satu butir per baris
  confirmLabel: string;
  busy: boolean;
  error: string | null;
  onConfirm: () => void;
}

/** Persetujuan sebelum penyelarasan berlaku atau dibatalkan (pola DeleteConsentDialog). */
export function ApplyAlignmentDialog({ open, onOpenChange, title, lines, confirmLabel, busy, error, onConfirm }: Props) {
  const t = useT();
  const [consent, setConsent] = useState(false);
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (open) setConsent(false);
  }, [open]);

  return (
    <AlertDialog open={open} onOpenChange={(next) => !busy && onOpenChange(next)}>
      <AlertDialogContent
        onOpenAutoFocus={(e) => {
          e.preventDefault();
          cancelRef.current?.focus();
        }}
        className="max-w-[calc(100vw-2rem)] sm:max-w-md"
      >
        <AlertDialogHeader>
          <AlertDialogTitle className="text-left font-semibold text-foreground">{title}</AlertDialogTitle>
          <AlertDialogDescription className="sr-only">{title}</AlertDialogDescription>
        </AlertDialogHeader>
        <ul className="list-disc list-inside space-y-1 py-1 text-left text-sm text-foreground">
          {lines.map((l) => (
            <li key={l}>{l}</li>
          ))}
        </ul>
        <div className="flex items-center gap-2">
          <Checkbox id="apply-consent" checked={consent} onCheckedChange={(c) => setConsent(c === true)} disabled={busy} />
          <label htmlFor="apply-consent" className="flex min-h-11 cursor-pointer items-center text-sm font-medium text-foreground">
            {t("cal.applyConsent")}
          </label>
        </div>
        {error && <p className="error text-sm">{error}</p>}
        <AlertDialogFooter>
          <AlertDialogCancel ref={cancelRef} disabled={busy} onClick={() => onOpenChange(false)} className="cursor-pointer">
            {t("cal.cancel")}
          </AlertDialogCancel>
          <Button disabled={!consent || busy} onClick={onConfirm} className="cursor-pointer">
            {busy ? t("cal.applying") : confirmLabel}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
