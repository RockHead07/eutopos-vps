"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { SearchBar } from "@/components/SearchBar";
import { DateRangePicker } from "@/components/DateRangePicker";
import { Panel } from "@/components/Panel";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { StatusBadge } from "@/components/StatusBadge";
import { Icon, VersionBadge } from "@/lib/Icon";
import Link from "@/lib/Link";
import { PageHead } from "@/lib/PageHead";
import { Rows } from "@/lib/Rows";
import { Thumbnail } from "@/components/Thumbnail";
import { Sparkline, type SparkPoint } from "@/lib/Sparkline";
import { api, formatDate, type Job } from "@/lib/api";
import {
  extractNameFromEmail,
  formatGreeting,
  getHourBucket,
  GREETINGS,
  type HourBucket,
} from "@/lib/greeting";
import { usePoll } from "@/lib/usePoll";

const BUSY = ["uploading", "queued", "running"];

const fmtDuration = (s: number) =>
  s < 60 ? `${Math.round(s)} s` : `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`;

/** Waktu dari ekstraksi fitur sampai rekonstruksi (tanpa mengekstrak frame dari video). Null kalau tidak tercatat. */
const buildSeconds = (j: Job) => {
  const t = j.summary?.run?.t_map_s;
  return t ? Object.values(t).reduce((a, b) => a + b, 0) : null;
};

function toLocalDateString(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (isNaN(d.getTime())) return null;
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function matchDate(itemDateIso: string | null | undefined, from: string, to: string): boolean {
  if (!from && !to) return true;
  const localDate = toLocalDateString(itemDateIso);
  if (!localDate) return false;
  if (from && localDate < from) return false;
  if (to && localDate > to) return false;
  return true;
}

export default function OverviewPage() {
  const router = useRouter();
  const jobs = usePoll(api.jobs, 5000);
  const versions = usePoll(api.versions, 10000);
  const service = usePoll(api.service, 5000);
  const { data: me, error: meError } = usePoll(api.me, 60000);
  const error = jobs.error ?? versions.error ?? service.error;

  const [mounted, setMounted] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState<string | null>(null);
  const currentBucketRef = useRef<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [areaFilter, setAreaFilter] = useState("all");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");

  useEffect(() => {
    setMounted(true);

    const pick = (bucket: HourBucket, weekday: number) => {
      let lastIndex: number | null = null;
      try {
        const stored = sessionStorage.getItem("eutopos.greeting.last");
        if (stored !== null) lastIndex = parseInt(stored, 10);
      } catch {
        // sessionStorage not available
      }

      const extras = GREETINGS.WEEKDAY[weekday];
      const hasExtras = Boolean(extras && extras.length > 0);
      const pickExtra = hasExtras && Math.random() < 0.25;

      let chosenTemplate: string;
      let chosenIndex: number;

      if (pickExtra && extras) {
        let idx = Math.floor(Math.random() * extras.length);
        if (lastIndex !== null && !isNaN(lastIndex) && idx === lastIndex && extras.length > 1) {
          idx = (idx + 1) % extras.length;
        }
        chosenIndex = idx;
        chosenTemplate = extras[idx];
      } else {
        const pool = GREETINGS[bucket];
        let idx = Math.floor(Math.random() * pool.length);
        if (lastIndex !== null && !isNaN(lastIndex) && idx === lastIndex && pool.length > 1) {
          idx = (idx + 1) % pool.length;
        }
        chosenIndex = idx;
        chosenTemplate = pool[idx];
      }

      try {
        sessionStorage.setItem("eutopos.greeting.last", String(chosenIndex));
      } catch {
        // ignore
      }

      currentBucketRef.current = bucket;
      setSelectedTemplate(chosenTemplate);
    };

    const now = new Date();
    const initialBucket = getHourBucket(now.getHours());
    pick(initialBucket, now.getDay());

    const interval = setInterval(() => {
      const currentNow = new Date();
      const b = getHourBucket(currentNow.getHours());
      if (b !== currentBucketRef.current) {
        pick(b, currentNow.getDay());
      }
    }, 60000);

    return () => clearInterval(interval);
  }, []);

  const name = extractNameFromEmail(me?.email);
  const title =
    !mounted || meError || !selectedTemplate
      ? "Overview"
      : formatGreeting(selectedTemplate, name);

  const allJobs = jobs.data ?? [];
  const allVersions = versions.data ?? [];

  const areaOptions = useMemo(() => {
    return Array.from(new Set(allJobs.map((j) => j.area_id))).sort();
  }, [allJobs]);

  const isFilterActive = areaFilter !== "all" || Boolean(fromDate || toDate);

  const handleResetFilters = () => {
    setAreaFilter("all");
    setFromDate("");
    setToDate("");
  };

  const handleSearchSubmit = () => {
    const q = searchQuery.trim();
    if (q) {
      router.push(`/jobs/?q=${encodeURIComponent(q)}`);
    } else {
      router.push("/jobs/");
    }
  };

  const filteredJobs = useMemo(() => {
    return allJobs.filter((j) => {
      if (areaFilter !== "all" && j.area_id !== areaFilter) return false;
      if (fromDate || toDate) {
        if (!matchDate(j.created_at, fromDate, toDate)) return false;
      }
      return true;
    });
  }, [allJobs, areaFilter, fromDate, toDate]);

  const filteredVersions = useMemo(() => {
    return allVersions.filter((v) => {
      if (areaFilter !== "all" && v.area_id !== areaFilter) return false;
      if (fromDate || toDate) {
        if (!matchDate(v.created_at, fromDate, toDate)) return false;
      }
      return true;
    });
  }, [allVersions, areaFilter, fromDate, toDate]);

  // Pekerjaan selesai yang punya foto uji, urut lama ke baru (id naik).
  const scored = filteredJobs
    .filter((j) => j.status === "done" && (j.summary?.inspect?.queries ?? 0) > 0)
    .sort((a, b) => a.id - b.id);
  const latest = filteredJobs.filter((j) => j.status === "done").sort((a, b) => b.id - a.id)[0];
  const counts = [
    { status: "done", label: "Done", n: filteredJobs.filter((j) => j.status === "done").length },
    {
      status: "running",
      label: "In progress",
      n: filteredJobs.filter((j) => BUSY.includes(j.status)).length,
    },
    { status: "failed", label: "Failed", n: filteredJobs.filter((j) => j.status === "failed").length },
  ];
  const s = service.data;
  // Maksimal 8 job selesai terakhir yang punya waktu tercatat, urut lama ke baru
  const builds: SparkPoint[] = filteredJobs
    .filter((j) => j.status === "done" && buildSeconds(j) !== null)
    .sort((a, b) => a.id - b.id)
    .slice(-8)
    .map((j) => ({
      id: j.id,
      value: buildSeconds(j)!,
      tip: `Job ${j.id} (${j.area_id}): ${fmtDuration(buildSeconds(j)!)}, ${
        j.summary?.run?.map_registered ?? "?"
      } of ${j.summary?.run?.map_images ?? "?"} frames registered`,
    }));
  const lastBuild = builds[builds.length - 1];

  const headerControls = (
    <div className="flex flex-col gap-2 w-full lg:w-auto">
      <div className="flex flex-col lg:flex-row items-stretch lg:items-center gap-2 w-full lg:w-auto lg:justify-end">
        {/* Search */}
        <div className="w-full lg:flex-1 lg:min-w-[360px] lg:max-w-xl">
          <SearchBar
            value={searchQuery}
            onChange={setSearchQuery}
            onSubmit={handleSearchSubmit}
            variant="hero"
            shortcut={true}
          />
        </div>

        {/* Filters row below lg, inline on lg+ */}
        <div className="flex items-center gap-2 w-full lg:w-auto">
          {/* Area */}
          <div className="flex-1 min-w-0 lg:w-36 lg:flex-none">
            <Select value={areaFilter} onValueChange={setAreaFilter}>
              <SelectTrigger className="w-full text-xs" aria-label="Filter by area">
                <SelectValue placeholder="All areas" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All areas</SelectItem>
                {areaOptions.map((a) => (
                  <SelectItem key={a} value={a}>
                    {a}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Date range */}
          <div className="flex-1 min-w-0 lg:flex-none">
            <DateRangePicker
              className="w-full lg:w-auto"
              value={{ from: fromDate || undefined, to: toDate || undefined }}
              onChange={(val) => {
                setFromDate(val.from || "");
                setToDate(val.to || "");
              }}
            />
          </div>
        </div>
      </div>

      {/* Filter status row */}
      {isFilterActive && (
        <div className="flex flex-wrap items-center gap-2 lg:justify-end">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span>
              Showing {filteredJobs.length} {filteredJobs.length === 1 ? "job" : "jobs"}
            </span>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={handleResetFilters}
              className="h-7 px-2 text-xs text-forest hover:text-forest-hover font-medium cursor-pointer"
            >
              Reset
            </Button>
          </div>
        </div>
      )}
    </div>
  );

  return (
    <>
      <PageHead crumbs={[{ label: "Overview" }]} title={title} controls={headerControls}>
        Map builds, map quality, and the map /localize is serving.
      </PageHead>
      {error && <p className="error">{error}</p>}
      <div className="overview">
        {/* Active map is NEVER filtered */}
        <Panel className="area-active">
          <span className="stat-label">Active map</span>
          {s ? (
            <>
              <span className="stat-value">
                {s.area_id ?? "none"}
                {s.map_version !== null && <small> v{s.map_version}</small>}
              </span>
              <span>
                {s.reloading ? (
                  <StatusBadge status="running">loading a new version</StatusBadge>
                ) : (
                  <StatusBadge status="done">ready</StatusBadge>
                )}
              </span>
            </>
          ) : (
            <span className="skeleton row" />
          )}
          {s?.reload_error && (
            <p className="error">
              <Icon name="error-map" /> {s.reload_error}
            </p>
          )}
          <h2>Recent versions</h2>
          {!versions.data && <Rows n={3} />}
          {versions.data && filteredVersions.length === 0 && (
            <p className="muted">
              {isFilterActive ? "No versions in this range" : "No map versions yet."}
            </p>
          )}
          <ul className="list">
            {[...filteredVersions]
              .sort((a, b) => b.id - a.id)
              .slice(0, 5)
              .map((v) => (
                <li key={v.id}>
                  <div>
                    <strong>
                      {v.area_id} v{v.version}
                    </strong>
                    <span className="muted">
                      {v.job_id ? <Link href={`/job/?id=${v.job_id}`}>job {v.job_id}</Link> : "from CLI"}
                    </span>
                  </div>
                  <VersionBadge status={v.status} />
                </li>
              ))}
          </ul>
          <Link href="/maps/">
            All map versions <Icon name="arrow-up-right" />
          </Link>
        </Panel>

        <Panel className="area-accept">
          <div>
            <h2>Test photos accepted</h2>
            <p className="muted">Share of each job&apos;s test photos localized with at least 50 inliers.</p>
          </div>
          {!jobs.data && <div className="skeleton block" />}
          {jobs.data && filteredJobs.length === 0 && <p className="muted">No jobs in this range</p>}
          {jobs.data && filteredJobs.length > 0 && scored.length === 0 && (
            <p className="muted">
              No finished job with a test video yet. Add a test video to a map session to see this.
            </p>
          )}
          {scored.length > 0 && <AcceptChart jobs={scored} />}
          <Link href="/jobs/">
            View as table <Icon name="arrow-up-right" />
          </Link>
        </Panel>

        <Panel className="area-jobs">
          <span className="stat-label">Jobs</span>
          <span className="stat-value">
            {jobs.data ? filteredJobs.length : <span className="skeleton row" />}
          </span>
          {jobs.data && filteredJobs.length === 0 ? (
            <p className="muted py-4 text-xs">No jobs in this range</p>
          ) : (
            <ul className="status-bars">
              {counts.map((c) => (
                <li key={c.status}>
                  <StatusBadge status={c.status}>{c.label}</StatusBadge>
                  <span className="track" aria-hidden="true">
                    <span
                      style={{
                        width: filteredJobs.length ? `${(c.n / filteredJobs.length) * 100}%` : "0%",
                      }}
                    />
                  </span>
                  <span className="num">{c.n}</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel className="area-build">
          <div>
            <h2>Map build time</h2>
            <p className="muted">From feature extraction to reconstruction, per finished job (GPU).</p>
          </div>
          {!jobs.data && <div className="skeleton block" />}
          {jobs.data && filteredJobs.length === 0 && <p className="muted">No jobs in this range</p>}
          {jobs.data && filteredJobs.length > 0 && !lastBuild && (
            <p className="muted">No finished job has a recorded build time yet.</p>
          )}
          {lastBuild && (
            <>
              <span className="stat-value">{fmtDuration(lastBuild.value)}</span>
              <Sparkline points={builds} />
            </>
          )}
        </Panel>

        <Panel className="area-latest">
          <div className="actions">
            <h2>Latest map</h2>
            {latest && <Link href={`/job/?id=${latest.id}`}>Job {latest.id} · {latest.area_id}</Link>}
          </div>
          {!jobs.data && <div className="skeleton block" />}
          {jobs.data && filteredJobs.length === 0 && <p className="muted">No jobs in this range</p>}
          {jobs.data && filteredJobs.length > 0 && !latest && <p className="muted">No finished job yet.</p>}
          {latest && <LatestStats job={latest} />}
        </Panel>
      </div>
    </>
  );
}

/** Satu seri: persen foto uji diterima per pekerjaan. Batang terbaru disorot dan diberi nilai. */
function AcceptChart({ jobs }: { jobs: Job[] }) {
  const last = jobs[jobs.length - 1].id;
  return (
    <div className="bars" role="img" aria-label="Test photos accepted per job">
      {jobs.map((j) => {
        const ins = j.summary!.inspect!;
        const pct = Math.round(((ins.accepted ?? 0) / (ins.queries ?? 1)) * 100);
        const tip = `Job ${j.id} (${j.area_id}): ${ins.accepted} of ${ins.queries} accepted, ${pct}%`;
        return (
          <Link
            key={j.id}
            href={`/job/?id=${j.id}`}
            className={j.id === last ? "bar latest" : "bar"}
            data-tip={tip}
            aria-label={tip}
          >
            {j.id === last && <span className="bar-value num">{pct}%</span>}
            <span className="bar-fill" style={{ height: `${Math.max(pct, 2)}%` }} />
            <span className="bar-label num">#{j.id}</span>
          </Link>
        );
      })}
    </div>
  );
}

function LatestStats({ job }: { job: Job }) {
  const petaVideo = job.videos?.find((v) => v.role === "peta");
  const recordedDate = petaVideo?.recorded_at ? formatDate(petaVideo.recorded_at) : "unknown";

  const run = job.summary?.run;
  const ins = job.summary?.inspect;
  const noTest = !ins?.queries; // 0 diterima dari 0 foto uji bukan hasil, hanya tidak ada video uji
  const items = [
    { label: "Registered frames", value: run?.map_registered, of: run?.map_images },
    { label: "Map pieces", value: ins?.parts?.length },
    {
      label: "Test photos accepted",
      value: noTest ? undefined : ins?.accepted,
      of: ins?.queries || undefined,
      note: noTest ? "No test video in this job" : undefined,
    },
  ];
  return (
    <div className="space-y-3">
      <Thumbnail
        jobId={job.id}
        hasPreview={job.has_preview}
        alt={`Preview for job ${job.id}`}
        aspect="card"
      />
      <p className="text-xs text-muted-foreground">Recorded {recordedDate}</p>
      <div className="stats-inline">
        {items.map((it) => (
          <div key={it.label}>
            <span className="stat-label">{it.label}</span>
            <span className="stat-value">
              {it.value ?? "-"}
              {it.of !== undefined && <small> / {it.of}</small>}
            </span>
            {it.note && <span className="muted">{it.note}</span>}
          </div>
        ))}
      </div>
    </div>
  );
}
