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

export type DeleteTarget =
  | {
      type: "job";
      id: number;
      area_id: string;
      has_version: boolean;
      has_frames: boolean;
    }
  | {
      type: "version";
      id: number;
      version: number;
      area_id: string;
      has_job: boolean;
    };

interface DeleteConsentDialogProps {
  target: DeleteTarget | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => Promise<void>;
  isDeleting: boolean;
  error: string | null;
  triggerRef?: React.RefObject<HTMLElement | null> | null;
}

export function DeleteConsentDialog({
  target,
  open,
  onOpenChange,
  onConfirm,
  isDeleting,
  error,
  triggerRef,
}: DeleteConsentDialogProps) {
  const [consent, setConsent] = useState(false);
  const cancelButtonRef = useRef<HTMLButtonElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const t = useT();

  useEffect(() => {
    if (open) {
      setConsent(false);
    }
  }, [open]);

  useEffect(() => {
    if (!open || isDeleting) return;
    const handlePointerDown = (e: MouseEvent | TouchEvent) => {
      if (contentRef.current && !contentRef.current.contains(e.target as Node)) {
        onOpenChange(false);
      }
    };
    document.addEventListener("mousedown", handlePointerDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
    };
  }, [open, isDeleting, onOpenChange]);

  if (!target) return null;

  const showKept = target.type === "job" ? target.has_frames : true;
  const keptKey =
    target.type === "version" && !target.has_job
      ? "dialog.keptMapFiles"
      : "dialog.keptFrames";
  const removedKey =
    target.type === "job"
      ? target.has_version
        ? "dialog.removedJobAndVersion"
        : "dialog.removedJobOnly"
      : target.has_job
        ? "dialog.removedJobAndVersion"
        : "dialog.removedDatabaseOnly";
  const title =
    target.type === "job"
      ? t("dialog.deleteJobTitle", { id: target.id, area: target.area_id })
      : t("dialog.deleteVersionTitle", { version: target.version, area: target.area_id });

  return (
    <AlertDialog open={open} onOpenChange={(next) => !isDeleting && onOpenChange(next)}>
      <AlertDialogContent
        ref={contentRef}
        onOpenAutoFocus={(e) => {
          e.preventDefault();
          cancelButtonRef.current?.focus();
        }}
        onCloseAutoFocus={(e) => {
          if (triggerRef?.current) {
            e.preventDefault();
            triggerRef.current.focus();
          }
        }}
        onEscapeKeyDown={(e) => {
          if (isDeleting) {
            e.preventDefault();
          } else {
            onOpenChange(false);
          }
        }}
        className="max-w-[calc(100vw-2rem)] sm:max-w-md"
      >
        <AlertDialogHeader>
          <AlertDialogTitle className="text-left font-semibold text-foreground">
            {title}
          </AlertDialogTitle>
          <AlertDialogDescription className="sr-only">
            {title}
          </AlertDialogDescription>
        </AlertDialogHeader>

        <div className="space-y-3 py-1 text-left">
          <div>
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
              {t("dialog.willBeRemoved")}
            </p>
            <ul className="list-disc list-inside text-sm text-foreground space-y-0.5 mt-1">
              <li>{t(removedKey)}</li>
            </ul>
          </div>

          {showKept && (
            <div>
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                {t("dialog.willBeKept")}
              </p>
              <ul className="list-disc list-inside text-sm text-foreground space-y-0.5 mt-1">
                <li>{t(keptKey)}</li>
              </ul>
            </div>
          )}

          <p className="text-sm font-semibold text-destructive">{t("dialog.cannotBeUndone")}</p>

          <div className="flex items-center gap-2 pt-2">
            <Checkbox
              id="delete-consent-checkbox"
              checked={consent}
              onCheckedChange={(checked) => setConsent(checked === true)}
              disabled={isDeleting}
            />
            <label
              htmlFor="delete-consent-checkbox"
              className="flex min-h-11 items-center text-sm font-medium leading-none cursor-pointer peer-disabled:cursor-not-allowed peer-disabled:opacity-70 text-foreground"
            >
              {t("dialog.consentCheckbox")}
            </label>
          </div>

          {error && <p className="error text-sm">{error}</p>}
        </div>

        <AlertDialogFooter>
          <AlertDialogCancel
            ref={cancelButtonRef}
            disabled={isDeleting}
            onClick={() => onOpenChange(false)}
            className="cursor-pointer"
          >
            {t("dialog.cancel")}
          </AlertDialogCancel>
          <Button
            variant="destructive"
            disabled={!consent || isDeleting}
            onClick={onConfirm}
            className="cursor-pointer"
          >
            {isDeleting ? t("dialog.deleting") : t("dialog.delete")}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
