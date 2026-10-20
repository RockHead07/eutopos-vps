/** Ringkasan pekerjaan aktif untuk banner Overview. Fungsi murni supaya bisa diuji tanpa browser. */
import type { Job } from "./api";

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

function stageLabel(job: Job): string {
  if (job.stage) return job.stage;
  if (job.status === "queued") return "waiting to start";
  return job.status;
}

function counted(count: number, singular: string, plural: string): string {
  return `${count} ${count === 1 ? singular : plural}`;
}

export function describeActive(summary: ActiveJobsSummary): {
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
    primary = `Building the map for ${single.area_id}`;
  } else if (runningCount === 0) {
    primary = "No job is running.";
  } else {
    const parts: string[] = [];
    if (buildCount > 0) {
      parts.push(`${counted(buildCount, "map build", "map builds")} running`);
    }
    if (uploadCount > 0) {
      parts.push(`${counted(uploadCount, "upload", "uploads")} in progress`);
    }
    primary = parts.join(", ");
  }

  const secondaryParts: string[] = [];
  if (single) {
    secondaryParts.push(`Job #${single.id}, stage: ${stageLabel(single)}`);
  }
  if (stalledCount > 0) {
    secondaryParts.push(
      `${counted(stalledCount, "upload", "uploads")} stopped receiving data`,
    );
  }

  return {
    primary,
    secondary: secondaryParts.length > 0 ? secondaryParts.join(" · ") : null,
  };
}
