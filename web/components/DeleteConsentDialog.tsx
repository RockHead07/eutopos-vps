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

export type DeleteTarget =
  | {
      type: "job";
      id: number;
      area_id: string;
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

  const hasJob = target.type === "job" || target.has_job;
  const title =
    target.type === "job"
      ? `Delete job ${target.id} (${target.area_id})?`
      : `Delete map version ${target.version} (${target.area_id})?`;

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
        className="max-w-md"
      >
        <AlertDialogHeader>
          <AlertDialogTitle className="text-left font-semibold text-foreground">
            {title}
          </AlertDialogTitle>
          <AlertDialogDescription className="sr-only">
            Confirmation required to delete {title}
          </AlertDialogDescription>
        </AlertDialogHeader>

        <div className="space-y-3 py-1 text-left">
          <div>
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
              Will be removed:
            </p>
            <ul className="list-disc list-inside text-sm text-foreground space-y-0.5 mt-1">
              <li>
                {hasJob
                  ? "The generated map files and the database rows of the job and version"
                  : "Only its database entry"}
              </li>
            </ul>
          </div>

          <div>
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
              Will be kept:
            </p>
            <ul className="list-disc list-inside text-sm text-foreground space-y-0.5 mt-1">
              <li>
                {hasJob ? "The extracted frames on the server" : "The map files on disk"}
              </li>
            </ul>
          </div>

          <p className="text-sm font-semibold text-destructive">This cannot be undone.</p>

          <div className="flex items-center gap-2 pt-2">
            <Checkbox
              id="delete-consent-checkbox"
              checked={consent}
              onCheckedChange={(checked) => setConsent(checked === true)}
              disabled={isDeleting}
            />
            <label
              htmlFor="delete-consent-checkbox"
              className="text-sm font-medium leading-none cursor-pointer peer-disabled:cursor-not-allowed peer-disabled:opacity-70 text-foreground"
            >
              I understand this cannot be undone
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
            Cancel
          </AlertDialogCancel>
          <Button
            variant="destructive"
            disabled={!consent || isDeleting}
            onClick={onConfirm}
            className="cursor-pointer"
          >
            {isDeleting ? "Deleting..." : "Delete"}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
