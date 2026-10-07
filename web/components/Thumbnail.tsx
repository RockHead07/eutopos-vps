"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";

interface ThumbnailProps {
  jobId: number | null | undefined;
  hasPreview: boolean | null | undefined;
  alt: string;
  className?: string;
  onClick?: () => void;
  aspect?: "table" | "card";
}

export function Thumbnail({
  jobId,
  hasPreview,
  alt,
  className,
  onClick,
  aspect = "table",
}: ThumbnailProps) {
  const [error, setError] = useState(false);

  const isCard = aspect === "card";
  const sizeClasses = isCard
    ? "w-full aspect-video rounded-xl border border-line/70"
    : "w-16 h-9 rounded-md border border-line/70";

  const showImage = Boolean(jobId && hasPreview && !error);

  const content = showImage ? (
    <img
      src={`/api/jobs/${jobId}/preview`}
      alt={alt}
      width={isCard ? 640 : 64}
      height={isCard ? 360 : 36}
      loading="lazy"
      onError={() => setError(true)}
      className={cn(sizeClasses, "object-cover", className)}
    />
  ) : (
    <div className={cn(sizeClasses, "bg-muted/60", className)} aria-hidden="true" />
  );

  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        className="block shrink-0 rounded-md cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-forest"
        aria-label={alt}
      >
        {content}
      </button>
    );
  }

  return content;
}
