"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { SearchBar } from "@/components/SearchBar";
import { DateRangePicker } from "@/components/DateRangePicker";
import { Panel } from "@/components/Panel";
import { ActiveJobsBanner } from "@/components/ActiveJobsBanner";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { StatusBadge } from "@/components/StatusBadge";
import { Icon, VersionBadge } from "@/lib/Icon";
import { useLocale, useT } from "@/lib/i18n";
import Link from "@/lib/Link";
import { PageHead } from "@/lib/PageHead";
import { Rows } from "@/lib/Rows";
import { Thumbnail } from "@/components/Thumbnail";
import { Sparkline, type SparkPoint } from "@/lib/Sparkline";
import { api, formatDate, type Job } from "@/lib/api";
import { BUSY } from "@/lib/activeJobs";
import {
  extractNameFromEmail,
  formatGreeting,
  getHourBucket,
  GREETINGS,
  type HourBucket,
} from "@/lib/greeting";
import { usePoll, useSharedPoll } from "@/lib/usePoll";

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

export default function OverviewPage() {
  const router = useRouter();
  const { locale } = useLocale();
  const t = useT();
  const service = useSharedPoll(api.service, 5000);
  const health = useSharedPoll(api.health, 10000);
  const jobs = usePoll(api.jobs, 5000);
  const versions = usePoll(api.versions, 5000);
  const me = usePoll(api.me, 60000);

  // Search state
  const [searchQuery, setSearchQuery] = useState("");

  // Filter state
  const [areaFilter, setAreaFilter] = useState<string>("all");
  const [fromDate, setFromDate] = useState<string>("");
  const [toDate, setToDate] = useState<string>("");

  const isFilterActive = areaFilter !== "all" || Boolean(fromDate) || Boolean(toDate);

  // Greetings template - calculated once on mount to avoid hydration mismatch
  const [greetingTemplate, setGreetingTemplate] = useState<string>("");
  useEffect(() => {
    const bucket: HourBucket = getHourBucket(new Date().getHours());
    const list = GREETINGS[bucket];
    const randomIndex = Math.floor(Math.random() * list.length);
    setGreetingTemplate(list[randomIndex]);
  }, []);

  const handleSearchSubmit = () => {
    const trimmed = searchQuery.trim();
    if (!trimmed) return;
    router.push(`/jobs/?q=${encodeURIComponent(trimmed)}`);
  };

  const allJobs = useMemo(() => jobs.data ?? [], [jobs.data]);
  const allVersions = useMemo(() => versions.data ?? [], [versions.data]);

  // Unique areas from jobs and versions
  const areaOptions = useMemo(() => {
    const areas = new Set<string>();
    allJobs.forEach((j) => {
      if (j.area_id) areas.add(j.area_id);
    });
    allVersions.forEach((v) => {
      if (v.area_id) areas.add(v.area_id);
    });
    return Array.from(areas).sort();
  }, [allJobs, allVersions]);

  // Filtered jobs
  const filteredJobs = useMemo(() => {
    return allJobs.filter((job) => {
      if (areaFilter !== "all" && job.area_id !== areaFilter) {
        return false;
      }
      const jobDate = toLocalDateString(job.created_at);
      if (jobDate) {
        if (fromDate && jobDate < fromDate) return false;
        if (toDate && jobDate > toDate) return false;
      }
      return true;
    });
  }, [allJobs, areaFilter, fromDate, toDate]);

  // Filtered versions (for recent versions list)
  const filteredVersions = useMemo(() => {
    return allVersions.filter((v) => {
      if (areaFilter !== "all" && v.area_id !== areaFilter) {
        return false;
      }
      const vDate = toLocalDateString(v.created_at);
      if (vDate) {
        if (fromDate && vDate < fromDate) return false;
        if (toDate && vDate > toDate) return false;
      }
      return true;
    });
  }, [allVersions, areaFilter, fromDate, toDate]);

  const handleResetFilters = () => {
    setAreaFilter("all");
    setFromDate("");
    setToDate("");
  };

  const title = useMemo(() => {
    if (isFilterActive) {
      return `${t("overview.pageTitle")} · ${filteredJobs.length} ${filteredJobs.length === 1 ? t("overview.showingJob") : t("overview.showingJobs", { count: filteredJobs.length })}`;
    }
    const name = extractNameFromEmail(me.data?.email);
    if (!name) return t("overview.systemOverview");
    return formatGreeting(greetingTemplate, name);
  }, [isFilterActive, filteredJobs.length, me.data?.email, greetingTemplate, t]);

  const s = service.data;
  const error = service.error || jobs.error || versions.error;

  const finished = filteredJobs.filter((j) => j.status === "done");
  const latest = finished[0];

  // Latest failed job
  const latestFailed = useMemo(() => {
    return filteredJobs.find((j) => j.status === "failed");
  }, [filteredJobs]);

  const scored = filteredJobs
    .filter((j) => j.status === "done" && j.summary?.inspect?.queries)
    .slice(0, 12)
    .reverse();

  const minInliers = Array.from(
    new Set(
      scored
        .map((j) => j.summary?.inspect?.min_inliers)
        .filter((v): v is number => typeof v === "number"),
    ),
  );

  const builds: SparkPoint[] = filteredJobs
    .filter((j) => j.status === "done")
    .map((j) => ({ id: j.id, value: buildSeconds(j) }))
    .filter((p): p is SparkPoint => p.value !== null)
    .slice(0, 15)
    .reverse();

  const lastBuild = builds[builds.length - 1];

  const counts = [
    {
      status: "done",
      label: t("overview.statusDone"),
      n: filteredJobs.filter((j) => j.status === "done").length,
    },
    {
      status: "running",
      label: t("overview.statusInProgress"),
      n: filteredJobs.filter((j) => BUSY.includes(j.status)).length,
    },
    {
      status: "failed",
      label: t("overview.statusFailed"),
      n: filteredJobs.filter((j) => j.status === "failed").length,
    },
  ];

  const headerControls = (
    <div className="flex flex-col gap-2.5 w-full">
      {/* Search and Filters flex row */}
      <div className="flex flex-col lg:flex-row items-stretch lg:items-center gap-2.5 w-full">
        {/* Search bar */}
        <div className="w-full lg:w-72">
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
              <SelectTrigger className="w-full text-xs cursor-pointer" aria-label={t("overview.filterAreaAria")}>
                <SelectValue placeholder={t("overview.allAreas")} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t("overview.allAreas")}</SelectItem>
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
              {filteredJobs.length === 1
                ? t("overview.showingJob")
                : t("overview.showingJobs", { count: filteredJobs.length })}
            </span>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={handleResetFilters}
              className="h-7 px-2 text-xs text-forest hover:text-forest-hover font-medium cursor-pointer"
            >
              {t("overview.clearFilters")}
            </Button>
          </div>
        </div>
      )}
    </div>
  );

  return (
    <>
      <PageHead crumbs={[{ label: t("nav.overview") }]} title={title} controls={headerControls}>
        {t("overview.subtitle")}
      </PageHead>
      {error && <p className="error">{error}</p>}
      <ActiveJobsBanner jobs={allJobs} />
      <div className="overview">
        {/* Active map is NEVER filtered */}
        <Panel className="area-active">
          <span className="stat-label">{t("overview.activeMap")}</span>
          {s ? (
            <>
              <span className="stat-value">
                {s.area_id ?? t("overview.none")}
                {s.map_version !== null && <small> v{s.map_version}</small>}
              </span>
              <div className="flex flex-wrap items-center gap-2">
                {s.reloading ? (
                  <StatusBadge status="running">{t("overview.loadingNewVersion")}</StatusBadge>
                ) : (
                  <StatusBadge status="done">{t("overview.ready")}</StatusBadge>
                )}
                {health.data?.aligned ? (
                  <span className="rounded bg-forest/15 px-2 py-0.5 text-[11px] font-semibold text-forest">
                    {t("overview.metricAligned")}
                  </span>
                ) : health.data ? (
                  <span
                    className="rounded bg-muted px-2 py-0.5 text-[11px] text-muted-foreground"
                    title={t("head.modelTitle")}
                  >
                    {t("overview.modelCoordinates")}
                  </span>
                ) : null}
              </div>
            </>
          ) : (
            <span className="skeleton row" />
          )}
          {s?.reload_error && (
            <p className="error">
              <Icon name="error-map" /> {s.reload_error}
            </p>
          )}
          <h2>{t("overview.recentVersions")}</h2>
          {!versions.data && <Rows n={3} />}
          {versions.data && filteredVersions.length === 0 && (
            <p className="muted">
              {isFilterActive ? t("overview.noVersionsRange") : t("overview.noVersionsYet")}
            </p>
          )}
          <ul className="list">
            {[...filteredVersions]
              .sort((a, b) => b.id - a.id)
              .slice(0, 5)
              .map((v) => {
                const isCurrentlyServing =
                  s && v.area_id === s.area_id && v.version === s.map_version;
                return (
                  <li key={v.id} className={isCurrentlyServing ? "bg-forest/5 rounded-md p-1" : undefined}>
                    <div>
                      <div className="flex items-center gap-1.5">
                        <strong>
                          {v.area_id} v{v.version}
                        </strong>
                        {isCurrentlyServing && (
                          <span className="text-[10px] font-semibold text-forest bg-forest/15 px-1.5 py-0.5 rounded">
                            {t("overview.servingBadge")}
                          </span>
                        )}
                      </div>
                      <span className="muted flex items-center gap-2 text-xs">
                        {v.job_id ? <Link href={`/job/?id=${v.job_id}`}>job {v.job_id}</Link> : t("overview.fromCli")}
                        {v.has_report && (
                          <a
                            href={`/api/versions/${v.id}/report`}
                            target="_blank"
                            rel="noreferrer"
                            className="text-forest hover:underline text-[11px]"
                          >
                            {t("overview.report3DLink")}
                          </a>
                        )}
                      </span>
                    </div>
                    <VersionBadge status={v.status} />
                  </li>
                );
              })}
          </ul>
          <Link href="/maps/">
            {t("overview.allMapVersions")} <Icon name="arrow-up-right" />
          </Link>
        </Panel>

        <Panel className="area-accept">
          <div>
            <h2>{t("overview.testPhotosAccepted")}</h2>
            <p className="muted">
              {t("overview.testPhotosShare", {
                min:
                  minInliers.length === 1 && minInliers[0] != null
                    ? minInliers[0]
                    : t("overview.theConfiguredNumber"),
              })}
            </p>
          </div>
          {!jobs.data && <div className="skeleton block" />}
          {jobs.data && filteredJobs.length === 0 && <p className="muted">{t("overview.noJobsRange")}</p>}
          {jobs.data && filteredJobs.length > 0 && scored.length === 0 && (
            <p className="muted">
              {t("overview.noTestVideoYet")}
            </p>
          )}
          {scored.length > 0 && <AcceptChart jobs={scored} t={t} />}
          <div className="flex items-center justify-between mt-2 pt-2 border-t border-line/50 text-[11px] text-muted-foreground">
            <span>{t("overview.inlierThreshold")}</span>
            <Link href="/jobs/">
              {t("overview.viewAsTable")} <Icon name="arrow-up-right" />
            </Link>
          </div>
        </Panel>

        <Panel className="area-jobs">
          <span className="stat-label">{t("overview.jobsCard")}</span>
          <span className="stat-value">
            {jobs.data ? filteredJobs.length : <span className="skeleton row" />}
          </span>
          {jobs.data && filteredJobs.length === 0 ? (
            <p className="muted py-4 text-xs">{t("overview.noJobsRange")}</p>
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
          {latestFailed && (
            <div className="mt-3 pt-2.5 border-t border-line/60 flex items-center justify-between text-xs">
              <div className="flex items-center gap-1.5 text-bad-fg">
                <span className="font-semibold">{t("overview.recentFailure")}</span>
                <span>Job #{latestFailed.id} {latestFailed.stage ? `(${latestFailed.stage})` : ""}</span>
              </div>
              <Link href={`/job/?id=${latestFailed.id}`} className="text-bad-fg hover:underline font-medium">
                {t("overview.viewDiagnosis")}
              </Link>
            </div>
          )}
        </Panel>

        <Panel className="area-build">
          <div>
            <h2>{t("overview.buildTimeTitle")}</h2>
            <p className="muted">{t("overview.buildTimeDesc")}</p>
          </div>
          {!jobs.data && <div className="skeleton block" />}
          {jobs.data && filteredJobs.length === 0 && <p className="muted">{t("overview.noJobsRange")}</p>}
          {jobs.data && filteredJobs.length > 0 && !lastBuild && (
            <p className="muted">{t("overview.noBuildTimeYet")}</p>
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
            <h2>{t("overview.latestMap")}</h2>
            {latest && <Link href={`/job/?id=${latest.id}`}>Job {latest.id} · {latest.area_id}</Link>}
          </div>
          {!jobs.data && <div className="skeleton block" />}
          {jobs.data && filteredJobs.length === 0 && <p className="muted">{t("overview.noJobsRange")}</p>}
          {jobs.data && filteredJobs.length > 0 && !latest && <p className="muted">{t("overview.noFinishedJob")}</p>}
          {latest && <LatestStats job={latest} locale={locale} t={t} />}
        </Panel>
      </div>
    </>
  );
}

/** Satu seri: persen foto uji diterima per pekerjaan. Batang terbaru disorot dan diberi nilai. */
function AcceptChart({
  jobs,
  t,
}: {
  jobs: Job[];
  t: (key: any, vars?: any) => string;
}) {
  const last = jobs[jobs.length - 1].id;
  return (
    <div className="bars" role="img" aria-label={t("overview.chartAria")}>
      {jobs.map((j) => {
        const ins = j.summary!.inspect!;
        const pct = Math.round(((ins.accepted ?? 0) / (ins.queries ?? 1)) * 100);
        const tip = t("overview.chartTip", {
          id: j.id,
          area: j.area_id,
          accepted: ins.accepted,
          queries: ins.queries,
          pct,
        });
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

function LatestStats({
  job,
  locale,
  t,
}: {
  job: Job;
  locale: string;
  t: (key: any, vars?: any) => string;
}) {
  const petaVideo = job.videos?.find((v) => v.role === "peta");
  const recordedDate = petaVideo?.recorded_at ? formatDate(petaVideo.recorded_at, locale) : "unknown";

  const run = job.summary?.run;
  const ins = job.summary?.inspect;
  const noTest = !ins?.queries; // 0 diterima dari 0 foto uji bukan hasil, hanya tidak ada video uji
  const items = [
    { label: t("overview.registeredFrames"), value: run?.map_registered, of: run?.map_images },
    { label: t("overview.mapPieces"), value: ins?.parts?.length },
    {
      label: t("overview.testPhotosAccepted"),
      value: noTest ? undefined : ins?.accepted,
      of: ins?.queries || undefined,
      note: noTest ? t("jobs.noTestVideo") : undefined,
    },
  ];
  return (
    <div className="space-y-3">
      <Thumbnail
        jobId={job.id}
        hasPreview={job.has_preview}
        alt={t("overview.previewJobAlt", { id: job.id })}
        aspect="card"
      />
      <p className="text-xs text-muted-foreground">{t("overview.recorded", { date: recordedDate })}</p>
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
