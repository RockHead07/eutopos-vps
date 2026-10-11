"use client";

import { useMemo, useState } from "react";
import { type Job, type Version, formatDate } from "@/lib/api";
import { VersionBadge } from "@/lib/Icon";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import Link from "@/lib/Link";
import { cn } from "@/lib/utils";

interface VersionComparisonPanelProps {
  versions: Version[];
  jobs: Job[];
  initialArea?: string;
  initialVersionIdA?: number;
  initialVersionIdB?: number;
  onClose?: () => void;
  className?: string;
}

function fmtSec(sec: number | null): string {
  if (sec === null) return "-";
  if (sec < 60) return `${Math.round(sec)}s`;
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return `${m}m ${s}s`;
}

export function VersionComparisonPanel({
  versions,
  jobs,
  initialArea,
  initialVersionIdA,
  initialVersionIdB,
  onClose,
  className,
}: VersionComparisonPanelProps) {
  // Find areas that have at least 2 versions
  const areaCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const v of versions) {
      counts[v.area_id] = (counts[v.area_id] ?? 0) + 1;
    }
    return counts;
  }, [versions]);

  const areasWithMultiple = useMemo(() => {
    return Object.keys(areaCounts)
      .filter((a) => areaCounts[a] >= 2)
      .sort();
  }, [areaCounts]);

  const defaultArea =
    initialArea && areaCounts[initialArea] >= 2
      ? initialArea
      : (areasWithMultiple[0] ?? versions[0]?.area_id ?? "");

  const [currentArea, setCurrentArea] = useState(defaultArea);

  const areaVersions = useMemo(() => {
    return versions.filter((v) => v.area_id === currentArea).sort((a, b) => b.version - a.version);
  }, [versions, currentArea]);

  const [versionAId, setVersionAId] = useState<number | null>(
    initialVersionIdA ?? areaVersions[0]?.id ?? null
  );
  const [versionBId, setVersionBId] = useState<number | null>(
    initialVersionIdB ?? areaVersions[1]?.id ?? areaVersions[0]?.id ?? null
  );

  const vA = areaVersions.find((v) => v.id === versionAId) ?? areaVersions[0];
  const vB = areaVersions.find((v) => v.id === versionBId) ?? areaVersions[1] ?? areaVersions[0];

  const jobA = vA?.job_id ? jobs.find((j) => j.id === vA.job_id) : undefined;
  const jobB = vB?.job_id ? jobs.find((j) => j.id === vB.job_id) : undefined;

  const runA = jobA?.summary?.run;
  const runB = jobB?.summary?.run;

  const insA = jobA?.summary?.inspect;
  const insB = jobB?.summary?.inspect;

  const buildSecA = runA?.t_map_s
    ? Object.values(runA.t_map_s).reduce((a, b) => a + b, 0)
    : null;
  const buildSecB = runB?.t_map_s
    ? Object.values(runB.t_map_s).reduce((a, b) => a + b, 0)
    : null;

  const regPctA =
    runA?.map_registered != null && runA?.map_images
      ? Math.round((runA.map_registered / runA.map_images) * 100)
      : null;
  const regPctB =
    runB?.map_registered != null && runB?.map_images
      ? Math.round((runB.map_registered / runB.map_images) * 100)
      : null;

  const acceptPctA =
    insA?.accepted != null && insA?.queries
      ? Math.round((insA.accepted / insA.queries) * 100)
      : null;
  const acceptPctB =
    insB?.accepted != null && insB?.queries
      ? Math.round((insB.accepted / insB.queries) * 100)
      : null;

  if (areaVersions.length < 2) {
    return (
      <div className={cn("rounded-lg border border-line bg-card p-4 text-xs", className)}>
        <div className="flex items-center justify-between border-b border-line pb-2 mb-2">
          <span className="font-semibold text-foreground">Version Comparison</span>
          {onClose && (
            <Button variant="ghost" size="sm" onClick={onClose} className="h-6 px-2 text-xs">
              Close
            </Button>
          )}
        </div>
        <p className="text-muted-foreground">
          At least two map versions for the same area are required to perform a comparison. Current area has {areaVersions.length} version.
        </p>
      </div>
    );
  }

  return (
    <div className={cn("flex flex-col gap-3 rounded-lg border border-line bg-card p-4 text-xs", className)}>
      {/* Header and area selector */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-line pb-3">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-foreground text-sm">Compare Map Versions</span>
          <span className="rounded bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
            Same Area Benchmark
          </span>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-muted-foreground text-[11px]">Area:</span>
          <Select
            value={currentArea}
            onValueChange={(val) => {
              setCurrentArea(val);
              const vers = versions.filter((v) => v.area_id === val);
              setVersionAId(vers[0]?.id ?? null);
              setVersionBId(vers[1]?.id ?? vers[0]?.id ?? null);
            }}
          >
            <SelectTrigger className="h-7 w-36 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Object.keys(areaCounts).map((a) => (
                <SelectItem key={a} value={a}>
                  {a} ({areaCounts[a]} {areaCounts[a] === 1 ? "version" : "versions"})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {onClose && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={onClose}
              className="h-7 px-2 text-xs text-muted-foreground hover:text-foreground cursor-pointer"
            >
              Close
            </Button>
          )}
        </div>
      </div>

      {/* Version Pickers */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {/* Version A Selector */}
        <div className="flex flex-col gap-1.5 rounded-md bg-canvas/60 p-3 border border-line/60">
          <div className="flex items-center justify-between">
            <span className="font-medium text-muted-foreground text-[11px]">Version A (Left)</span>
            {vA && <VersionBadge status={vA.status} />}
          </div>
          <Select
            value={String(vA?.id ?? "")}
            onValueChange={(val) => setVersionAId(Number(val))}
          >
            <SelectTrigger className="h-8 text-xs font-semibold">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {areaVersions.map((v) => (
                <SelectItem key={v.id} value={String(v.id)}>
                  v{v.version} · {v.status} {v.job_id ? `(Job #${v.job_id})` : "(CLI)"}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <div className="flex items-center justify-between text-[11px] text-muted-foreground mt-1">
            <span>Created {vA ? formatDate(vA.created_at) : "-"}</span>
            {vA?.job_id && (
              <Link href={`/job/?id=${vA.job_id}`} className="text-forest hover:underline">
                Job #{vA.job_id}
              </Link>
            )}
          </div>
        </div>

        {/* Version B Selector */}
        <div className="flex flex-col gap-1.5 rounded-md bg-canvas/60 p-3 border border-line/60">
          <div className="flex items-center justify-between">
            <span className="font-medium text-muted-foreground text-[11px]">Version B (Right)</span>
            {vB && <VersionBadge status={vB.status} />}
          </div>
          <Select
            value={String(vB?.id ?? "")}
            onValueChange={(val) => setVersionBId(Number(val))}
          >
            <SelectTrigger className="h-8 text-xs font-semibold">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {areaVersions.map((v) => (
                <SelectItem key={v.id} value={String(v.id)}>
                  v{v.version} · {v.status} {v.job_id ? `(Job #${v.job_id})` : "(CLI)"}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <div className="flex items-center justify-between text-[11px] text-muted-foreground mt-1">
            <span>Created {vB ? formatDate(vB.created_at) : "-"}</span>
            {vB?.job_id && (
              <Link href={`/job/?id=${vB.job_id}`} className="text-forest hover:underline">
                Job #{vB.job_id}
              </Link>
            )}
          </div>
        </div>
      </div>

      {/* Metrics Comparison Table */}
      <div className="rounded-md border border-line overflow-hidden mt-1">
        <table className="w-full text-left text-xs">
          <thead className="bg-canvas/80 border-b border-line text-muted-foreground font-medium">
            <tr>
              <th className="p-2.5">Reconstruction Metric</th>
              <th className="p-2.5 w-1/3">
                v{vA?.version ?? "A"} {vA?.status === "published" && "(Active)"}
              </th>
              <th className="p-2.5 w-1/3">
                v{vB?.version ?? "B"} {vB?.status === "published" && "(Active)"}
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {/* Status */}
            <tr>
              <td className="p-2.5 font-medium text-foreground">Publication Status</td>
              <td className="p-2.5 capitalize">{vA?.status ?? "-"}</td>
              <td className="p-2.5 capitalize">{vB?.status ?? "-"}</td>
            </tr>

            {/* Registered frames */}
            <tr>
              <td className="p-2.5">
                <div className="font-medium text-foreground">Registered Frames</div>
                <div className="text-[11px] text-muted-foreground">Reconstruction frame coverage</div>
              </td>
              <td className="p-2.5 font-mono">
                {runA ? (
                  <div>
                    <span className="font-semibold text-foreground">
                      {runA.map_registered ?? "-"} / {runA.map_images ?? "-"}
                    </span>
                    {regPctA !== null && (
                      <span className="ml-1.5 text-muted-foreground text-[11px]">({regPctA}%)</span>
                    )}
                  </div>
                ) : (
                  <span className="text-muted-foreground">-</span>
                )}
              </td>
              <td className="p-2.5 font-mono">
                {runB ? (
                  <div>
                    <span className="font-semibold text-foreground">
                      {runB.map_registered ?? "-"} / {runB.map_images ?? "-"}
                    </span>
                    {regPctB !== null && (
                      <span className="ml-1.5 text-muted-foreground text-[11px]">({regPctB}%)</span>
                    )}
                  </div>
                ) : (
                  <span className="text-muted-foreground">-</span>
                )}
              </td>
            </tr>

            {/* Map pieces */}
            <tr>
              <td className="p-2.5">
                <div className="font-medium text-foreground">Map Pieces</div>
                <div className="text-[11px] text-muted-foreground">Connected SfM components</div>
              </td>
              <td className="p-2.5 font-mono">
                {insA?.parts ? (
                  <span
                    className={cn(
                      "font-semibold",
                      insA.parts.length === 1 ? "text-forest" : "text-amber-700"
                    )}
                  >
                    {insA.parts.length} {insA.parts.length === 1 ? "(Connected)" : "(Split)"}
                  </span>
                ) : (
                  <span className="text-muted-foreground">-</span>
                )}
              </td>
              <td className="p-2.5 font-mono">
                {insB?.parts ? (
                  <span
                    className={cn(
                      "font-semibold",
                      insB.parts.length === 1 ? "text-forest" : "text-amber-700"
                    )}
                  >
                    {insB.parts.length} {insB.parts.length === 1 ? "(Connected)" : "(Split)"}
                  </span>
                ) : (
                  <span className="text-muted-foreground">-</span>
                )}
              </td>
            </tr>

            {/* Test photos accepted */}
            <tr>
              <td className="p-2.5">
                <div className="font-medium text-foreground">Test Queries Accepted</div>
                <div className="text-[11px] text-muted-foreground">
                  Inlier threshold &ge; {insA?.min_inliers ?? insB?.min_inliers ?? 50}
                </div>
              </td>
              <td className="p-2.5 font-mono">
                {insA?.queries ? (
                  <div>
                    <span className="font-semibold text-foreground">
                      {insA.accepted ?? 0} / {insA.queries}
                    </span>
                    {acceptPctA !== null && (
                      <span className="ml-1.5 text-muted-foreground text-[11px]">({acceptPctA}%)</span>
                    )}
                  </div>
                ) : (
                  <span className="text-muted-foreground">No test video</span>
                )}
              </td>
              <td className="p-2.5 font-mono">
                {insB?.queries ? (
                  <div>
                    <span className="font-semibold text-foreground">
                      {insB.accepted ?? 0} / {insB.queries}
                    </span>
                    {acceptPctB !== null && (
                      <span className="ml-1.5 text-muted-foreground text-[11px]">({acceptPctB}%)</span>
                    )}
                  </div>
                ) : (
                  <span className="text-muted-foreground">No test video</span>
                )}
              </td>
            </tr>

            {/* Map build time */}
            <tr>
              <td className="p-2.5">
                <div className="font-medium text-foreground">Build Duration</div>
                <div className="text-[11px] text-muted-foreground">Feature extraction to SfM</div>
              </td>
              <td className="p-2.5 font-mono text-muted-foreground">{fmtSec(buildSecA)}</td>
              <td className="p-2.5 font-mono text-muted-foreground">{fmtSec(buildSecB)}</td>
            </tr>

            {/* 3D Inspection Report Links */}
            <tr>
              <td className="p-2.5 font-medium text-foreground">3D Inspection Report</td>
              <td className="p-2.5">
                {vA?.has_report ? (
                  <a
                    href={`/api/versions/${vA.id}/report`}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 text-forest hover:underline font-medium"
                  >
                    Open 3D Report ↗
                  </a>
                ) : (
                  <span className="text-muted-foreground">-</span>
                )}
              </td>
              <td className="p-2.5">
                {vB?.has_report ? (
                  <a
                    href={`/api/versions/${vB.id}/report`}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 text-forest hover:underline font-medium"
                  >
                    Open 3D Report ↗
                  </a>
                ) : (
                  <span className="text-muted-foreground">-</span>
                )}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* Semantic notice */}
      <div className="rounded bg-canvas/70 p-2 text-[11px] text-muted-foreground border border-line/60 leading-relaxed">
        <strong>Terminology note:</strong> Registered frames and test query acceptance rates describe SfM feature matching and continuity. They do not constitute ground-truth physical metric localization accuracy in meters. Physical metric coordinates require measured ground-truth reference points (align.json).
      </div>
    </div>
  );
}
