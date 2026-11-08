"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { SplatViewer } from "@/components/SplatViewer";

function SplatPageContent() {
  const searchParams = useSearchParams();
  const rawVersion = searchParams.get("version");
  const versionId = rawVersion ? parseInt(rawVersion, 10) : null;
  const camParam = searchParams.get("cam");

  return <SplatViewer versionId={versionId} camParam={camParam} />;
}

export default function SplatPage() {
  // useSearchParams wajib di dalam Suspense pada static export.
  return (
    <Suspense
      fallback={
        <div className="flex h-screen items-center justify-center p-6">
          <p className="text-sm text-muted-foreground">...</p>
        </div>
      }
    >
      <SplatPageContent />
    </Suspense>
  );
}
