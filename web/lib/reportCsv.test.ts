import { test } from "node:test";
import assert from "node:assert/strict";
// @ts-expect-error Node's type stripping requires the .ts extension.
import { reportColumns, reportCsv } from "./reportCsv.ts";
import type { Job } from "./api";

function makeJob(overrides: Partial<Job>): Job {
  return {
    id: 1,
    area_id: "floor10",
    status: "done",
    stage: "gate",
    created_by: "a@x.id",
    videos: [],
    summary: null,
    error: null,
    map_version_id: 1,
    created_at: "2026-11-25T10:00:00+00:00",
    started_at: "2026-11-25T10:01:00+00:00",
    finished_at: "2026-11-25T10:05:00+00:00",
    ...overrides,
  };
}

const jobWithReport = makeJob({
  id: 10,
  area_id: "floor10",
  summary: {
    report: {
      version: 1,
      computed_at: "2026-11-25T10:05:00+00:00",
      recording: {
        source: "arcore",
        duration_s: 120.5,
        path_length_m: 42.3,
        footprint_m2: 98.5,
        footprint: {
          method: "trajectory_buffer",
          radius_m: 1.0,
          cell_m: 0.25,
          frame: "aligned_sfm",
        },
        device_model: "TECNO KL7",
        warnings: ["multi_floor"],
      },
      network: {
        uploads: [{ role: "peta", kind: "frames", size_bytes: 1000, seconds: 2, mbps: 4 }],
        total_bytes: 1000,
        seconds: 2,
        mbps: 4.0,
      },
      processing: {
        queue_s: 5.0,
        gpu_wait_s: 0.2,
        total_s: 240.0,
      },
      quality: {
        registered: 80,
        images: 82,
        mean_reprojection_error_px: 0.91,
        gate: { decision: "publish", reasons: [], queries: 10, accepted: 9 },
      },
    },
  },
});

const jobWithoutReport = makeJob({
  id: 11,
  area_id: "lab10",
  summary: null,
});

test("job without report still gets a row", () => {
  const cols = reportColumns([jobWithReport, jobWithoutReport]);
  assert.deepEqual(cols.slice(0, 6), [
    "id",
    "area_id",
    "status",
    "created_at",
    "report.version",
    "report.error",
  ]);
  assert.ok(cols.includes("recording.duration_s"));
  assert.ok(!cols.includes("network.uploads"));
  assert.ok(!cols.includes("recording.warnings"));
  assert.ok(!cols.includes("quality.gate.reasons"));

  const csv = reportCsv([jobWithReport, jobWithoutReport]);
  const lines = csv.split("\r\n").filter(Boolean);
  assert.equal(lines.length, 1 + 1 + 2);
  assert.equal(lines[0], "# rows: 2");
  assert.equal(lines[1], cols.join(","));
  assert.ok(lines[3].startsWith("11,lab10,done,2026-11-25T10:00:00+00:00,,"));
});

test("error card fills report.error", () => {
  const errJob = makeJob({
    id: 12,
    summary: {
      report: {
        version: 1,
        error: "failed reading sfm",
      },
    },
  });
  const cols = reportColumns([errJob]);
  const csv = reportCsv([errJob]);
  const lines = csv.split("\r\n").filter(Boolean);
  const row = lines[2].split(",");
  assert.equal(row[cols.indexOf("report.version")], "1");
  assert.equal(row[cols.indexOf("report.error")], "failed reading sfm");
});

test("values with commas and quotes are escaped", () => {
  const special = makeJob({
    id: 13,
    summary: {
      report: {
        version: 1,
        recording: {
          device_model: 'A, "B"',
        },
      },
    },
  });
  const cols = reportColumns([special]);
  const csv = reportCsv([special]);
  const lines = csv.split("\r\n").filter(Boolean);
  const idx = cols.indexOf("recording.device_model");
  assert.ok(idx >= 6);
  assert.ok(lines[2].includes('"A, ""B"""'));
});

test("null becomes empty cell, not 0", () => {
  const videoJob = makeJob({
    id: 14,
    summary: {
      report: {
        version: 1,
        recording: {
          source: "video",
          duration_s: 95.0,
          path_length_m: null,
          path_length_m_reason: "no_arcore",
          footprint: null,
        },
        network: {
          uploads: null,
          uploads_reason: "cli_job",
          mbps: null,
        },
      },
    },
  });
  const cols = reportColumns([videoJob]);
  assert.ok(cols.includes("recording.path_length_m"));
  assert.ok(!cols.includes("network.uploads"));
  const csv = reportCsv([videoJob]);
  const lines = csv.split("\r\n").filter(Boolean);
  const cells = lines[2].split(",");
  assert.equal(cells[cols.indexOf("recording.path_length_m")], "");
  assert.equal(cells[cols.indexOf("network.mbps")], "");
  assert.equal(cells[cols.indexOf("recording.duration_s")], "95");
});
