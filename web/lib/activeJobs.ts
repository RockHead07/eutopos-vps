/** Ringkasan pekerjaan aktif untuk banner Overview. Fungsi murni supaya bisa diuji tanpa browser. */
import type { Job } from "./api";
import type { TranslationKey } from "./i18n";

export const BUSY = ["uploading", "queued", "running"];

export type ActiveJobsSummary = {
  building: Job[];
  uploading: Job[];
  stalled: Job[];
};

const newestFirst = (a: Job, b: Job) => b.id - a.id;

export function summarizeActiveJobs(jobs: Job[]): ActiveJobsSummary {
  const active = jobs.filter((job) => BUSY.includes(job.status));
  return {
    building: active
      .filter((job) => job.stalled !== true && (job.status === "queued" || job.status === "running"))
      .sort(newestFirst),
    uploading: active
      .filter((job) => job.stalled !== true && job.status === "uploading")
      .sort(newestFirst),
    stalled: active.filter((job) => job.stalled === true).sort(newestFirst),
  };
}

type TranslateFn = (key: TranslationKey, vars?: Record<string, string | number>) => string;

function stageLabel(job: Job, t?: TranslateFn): string {
  if (job.stage) return job.stage;
  if (job.status === "queued") return t ? t("banner.waitingToStart") : "waiting to start";
  return job.status;
}

export function describeActive(
  summary: ActiveJobsSummary,
  t?: TranslateFn,
): {
  primary: string;
  secondary: string | null;
} {
  const buildCount = summary.building.length;
  const uploadCount = summary.uploading.length;
  const runningCount = buildCount + uploadCount;
  const stalledCount = summary.stalled.length;
  const single = buildCount === 1 && uploadCount === 0 ? summary.building[0] : null;

  let primary: string;
  if (single) {
    primary = t ? t("banner.buildingMap", { area: single.area_id }) : `Building the map for ${single.area_id}`;
  } else if (runningCount === 0) {
    primary = t ? t("banner.noJobRunning") : "No job is running.";
  } else {
    const parts: string[] = [];
    if (buildCount > 0) {
      parts.push(
        t
          ? buildCount === 1
            ? t("banner.mapBuildRunning")
            : t("banner.mapBuildsRunning", { count: buildCount })
          : `${buildCount} ${buildCount === 1 ? "map build" : "map builds"} running`,
      );
    }
    if (uploadCount > 0) {
      parts.push(
        t
          ? uploadCount === 1
            ? t("banner.uploadInProgress")
            : t("banner.uploadsInProgress", { count: uploadCount })
          : `${uploadCount} ${uploadCount === 1 ? "upload" : "uploads"} in progress`,
      );
    }
    primary = parts.join(", ");
  }

  const secondaryParts: string[] = [];
  if (single) {
    secondaryParts.push(
      t
        ? t("banner.jobStage", { id: single.id, stage: stageLabel(single, t) })
        : `Job #${single.id}, stage: ${stageLabel(single)}`,
    );
  }
  if (stalledCount > 0) {
    secondaryParts.push(
      t
        ? stalledCount === 1
          ? t("banner.uploadStoppedData")
          : t("banner.uploadsStoppedData", { count: stalledCount })
        : `${stalledCount} ${stalledCount === 1 ? "upload" : "uploads"} stopped receiving data`,
    );
  }

  return {
    primary,
    secondary: secondaryParts.length > 0 ? secondaryParts.join(" · ") : null,
  };
}
