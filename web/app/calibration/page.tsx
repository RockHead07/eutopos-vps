"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ApplyAlignmentDialog } from "@/components/ApplyAlignmentDialog";
import { CalibrationPlot } from "@/components/CalibrationPlot";
import { Panel } from "@/components/Panel";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  api,
  areaApi,
  calibrationApi,
  formatDate,
  type AlignmentRow,
  type ApiError,
  type CalFit,
  type CalImport,
  type CalRole,
  type Version,
} from "@/lib/api";
import { checkDistance, parsePoints, pointsProblem, withRoles } from "@/lib/calibration";
import { useLocale, useT, type TranslationKey } from "@/lib/i18n";
import Link from "@/lib/Link";
import { PageHead } from "@/lib/PageHead";
import { usePoll } from "@/lib/usePoll";

const CODES = ["too_few_reference", "collinear", "no_observation", "fit_failed", "bad_scale", "bad_input"];
const m2 = (v: number | null | undefined) => (v === null || v === undefined ? "-" : v.toFixed(2));

type Moves = { rooms: number; strokes: number; edits: number };
type Pending = { kind: "apply" } | { kind: "revert"; row: AlignmentRow };

function OriginFigure({ alt }: { alt: string }) {
  return (
    <svg viewBox="0 0 140 100" role="img" aria-label={alt} className="h-auto w-40">
      <g stroke="var(--foreground)" strokeWidth={1.5} fill="none">
        <line x1={20} y1={80} x2={120} y2={80} />
        <line x1={20} y1={80} x2={20} y2={14} />
        <path d="M114,75 L121,80 L114,85" />
        <path d="M15,21 L20,13 L25,21" />
      </g>
      <circle cx={20} cy={80} r={4} fill="var(--primary)" />
      <text x={26} y={94} fontSize={10} fill="var(--foreground)">0,0</text>
      <text x={112} y={72} fontSize={10} fill="var(--foreground)">+x</text>
      <text x={28} y={20} fontSize={10} fill="var(--foreground)">+y</text>
    </svg>
  );
}

function CalibrationPage() {
  const versionId = Number(useSearchParams().get("version") ?? "");
  const t = useT();
  const { locale } = useLocale();
  const { data: me } = usePoll(api.me, 60000);
  const admin = !!me?.is_admin;

  const [version, setVersion] = useState<Version | null | undefined>(undefined);
  const [text, setText] = useState("");
  const [roles, setRoles] = useState<Record<string, CalRole>>({});
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [measured, setMeasured] = useState("");
  const [setId, setSetId] = useState<number | null>(null);
  const [saved, setSaved] = useState<{ id: number; count: number } | null>(null);
  const [imported, setImported] = useState<CalImport | null>(null);
  const [accepted, setAccepted] = useState(0);
  const [fit, setFit] = useState<CalFit | null>(null);
  const [history, setHistory] = useState<AlignmentRow[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [republish, setRepublish] = useState(false);
  const [pending, setPending] = useState<Pending | null>(null);
  const [open, setOpen] = useState(false); // terpisah dari pending: isi dialog tetap utuh saat animasi tutup
  const [counts, setCounts] = useState<Moves | null>(null);
  const [dialogError, setDialogError] = useState<string | null>(null);

  const parsed = useMemo(() => parsePoints(text), [text]);
  const points = useMemo(() => withRoles(parsed.points, roles), [parsed.points, roles]);
  const problem = points.length > 0 ? pointsProblem(points) : null;
  const check = checkDistance(
    parsed.points.find((p) => p.point_id === from),
    parsed.points.find((p) => p.point_id === to),
    Number(measured),
  );
  const locked = setId !== null;
  const current = history.find((h) => h.status === "applied") ?? null;

  const errText = useCallback(
    (e: unknown) => {
      const err = e as ApiError;
      if (err.code && CODES.includes(err.code)) return t(`cal.err.${err.code}` as TranslationKey);
      if (/alignment changed/.test(err.message)) return t("cal.stale");
      return err.message;
    },
    [t],
  );

  const loadHistory = useCallback(async () => {
    try {
      setHistory(await calibrationApi.alignments(versionId));
    } catch (e) {
      setError(errText(e));
    }
  }, [versionId, errText]);

  useEffect(() => {
    if (!Number.isInteger(versionId) || versionId <= 0) return;
    api.versions().then(
      (all) => setVersion(all.find((v) => v.id === versionId) ?? null),
      (e) => setError(errText(e)),
    );
    loadHistory();
  }, [versionId, loadHistory, errText]);

  async function run(name: string, fn: () => Promise<void>) {
    setBusy(name);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(null);
    }
  }

  const savePoints = () =>
    run("save", async () => {
      const r = await calibrationApi.createSet(versionId, points);
      setSetId(r.id);
      setSaved({ id: r.id, count: points.length });
    });

  const importFile = (file: File) =>
    run("import", async () => {
      if (setId === null) return;
      const r = await calibrationApi.importObservations(setId, await file.text());
      setImported(r);
      setAccepted((n) => n + r.accepted);
      setFit(null);
    });

  const calculate = () =>
    run("fit", async () => {
      if (setId !== null) setFit(await calibrationApi.fit(setId));
    });

  function newSet() {
    setSetId(null);
    setSaved(null);
    setImported(null);
    setAccepted(0);
    setFit(null);
    setMessage(null);
  }

  async function openDialog(p: Pending) {
    setDialogError(null);
    setCounts(null);
    setPending(p);
    setOpen(true);
    if (version?.status !== "published") return;
    try {
      // Sebaiknya tahu berapa yang akan dipindah; bila area belum dilayani, ringkasan jadi umum saja.
      const [g, w] = await Promise.all([areaApi.graph(version.area_id), areaApi.walkable(version.area_id)]);
      setCounts({ rooms: g.rooms.length, edits: g.edits.length, strokes: w.strokes.length });
    } catch {}
  }

  async function confirm() {
    if (!pending) return;
    setBusy("apply");
    setDialogError(null);
    try {
      const base = current?.id ?? null;
      const r =
        pending.kind === "apply"
          ? await calibrationApi.apply(setId as number, base)
          : await calibrationApi.revert(pending.row.id, base);
      setRepublish(r.republish_required);
      setMessage(
        pending.kind === "apply"
          ? t("cal.applied", { id: r.alignment_id, ...r.moved })
          : t("cal.reverted", { id: pending.row.id }),
      );
      setOpen(false);
      await loadHistory();
    } catch (e) {
      setDialogError(errText(e));
    } finally {
      setBusy(null);
    }
  }

  if (!Number.isInteger(versionId) || versionId <= 0) return <p className="error">{t("cal.noVersion")}</p>;
  if (version === null) return <p className="error">{t("cal.versionNotFound")}</p>;

  const area = version?.area_id ?? "";
  const canSave = admin && !locked && points.length > 0 && parsed.errors.length === 0 && !problem;
  const canCalc = admin && locked && accepted > 0 && !!check?.ok;
  const why = !locked ? t("cal.needSet") : accepted === 0 ? t("cal.needImport") : !check?.ok ? t("cal.needCheck") : null;
  const dialogTitle =
    pending?.kind === "revert"
      ? t("cal.revertTitle", { id: pending.row.id })
      : t("cal.applyTitle", { version: version?.version ?? "" });
  const dialogLines: string[] = [];
  if (pending?.kind === "apply" && fit) {
    dialogLines.push(
      current
        ? t("cal.applyScale", { from: current.scale.toFixed(6), to: fit.stats.scale.toFixed(6) })
        : t("cal.applyFirst"),
    );
  }
  if (pending?.kind === "revert") {
    dialogLines.push(
      t("cal.applyScale", { from: (current?.scale ?? 0).toFixed(6), to: pending.row.scale.toFixed(6) }),
      t("cal.revertBody"),
    );
  }
  if (version?.status === "published" && (current || pending?.kind === "revert")) {
    dialogLines.push(counts ? t("cal.applyMoves", counts) : t("cal.applyMovesUnknown"));
    dialogLines.push(t("cal.applyRepublish"));
  }

  return (
    <>
      <PageHead
        crumbs={[{ label: t("nav.mapVersions"), href: "/maps/" }, { label: area || String(versionId) }]}
        title={t("cal.pageTitle", { id: area || versionId })}
      >
        <p className="mt-1 text-xs text-muted-foreground">{t("cal.pageDesc")}</p>
      </PageHead>
      {error && <p className="error">{error}</p>}
      {message && <p className="text-sm">{message}</p>}
      {!admin && me && <p className="text-xs text-muted-foreground">{t("cal.adminOnly")}</p>}
      {republish && (
        <Panel className="border border-[var(--bad-fg)]">
          <span className="text-sm font-semibold">{t("cal.republishTitle")}</span>
          <span className="text-sm">{t("cal.republishBody")}</span>
          <div>
            <Link className="text-sm underline" href={`/area/?id=${encodeURIComponent(area)}`}>
              {t("cal.republishLink")}
            </Link>
          </div>
        </Panel>
      )}

      <Panel>
        <span className="stat-label">{t("cal.stepPoints")}</span>
        <p className="text-xs text-muted-foreground">{t("cal.pointsHint")}</p>
        <div className="flex flex-wrap items-start gap-4">
          <div className="flex min-w-0 flex-1 basis-64 flex-col gap-2">
            <textarea
              aria-label={t("cal.pointsAria")}
              className="min-h-32 w-full rounded-md border border-border bg-transparent p-2 font-mono text-sm"
              placeholder={t("cal.pointsPlaceholder")}
              value={text}
              disabled={locked || !admin}
              onChange={(e) => setText(e.target.value)}
            />
            {parsed.errors.map((e) => (
              <span key={`${e.line}-${e.message}`} className="error text-xs">
                {e.line > 0
                  ? t("cal.parseError", { line: e.line, problem: t(`cal.parse.${e.message}` as TranslationKey) })
                  : t(`cal.parse.${e.message}` as TranslationKey)}
              </span>
            ))}
            {problem && <span className="error text-xs">{t(`cal.problem.${problem}` as TranslationKey)}</span>}
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-xs font-semibold">{t("cal.originTitle")}</span>
            <OriginFigure alt={t("cal.originAlt")} />
            <p className="max-w-56 text-xs text-muted-foreground">{t("cal.originHint")}</p>
          </div>
        </div>

        {points.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("cal.colPoint")}</TableHead>
                <TableHead>{t("cal.colX")}</TableHead>
                <TableHead>{t("cal.colY")}</TableHead>
                <TableHead>{t("cal.colRole")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {points.map((p) => (
                <TableRow key={p.point_id}>
                  <TableCell>{p.point_id}</TableCell>
                  <TableCell>{p.x_m}</TableCell>
                  <TableCell>{p.y_m}</TableCell>
                  <TableCell>
                    <select
                      aria-label={t("cal.roleAria", { id: p.point_id })}
                      className="rounded-md border border-border bg-transparent p-1 text-sm"
                      value={p.role}
                      disabled={locked || !admin}
                      onChange={(e) => setRoles({ ...roles, [p.point_id]: e.target.value as CalRole })}
                    >
                      <option value="reference">{t("cal.roleReference")}</option>
                      <option value="test">{t("cal.roleTest")}</option>
                    </select>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}

        <div className="flex flex-col gap-2 rounded-md border border-border p-3">
          <span className="text-xs font-semibold">{t("cal.checkTitle")}</span>
          <p className="text-xs text-muted-foreground">{t("cal.checkHint")}</p>
          <div className="flex flex-wrap items-end gap-2 text-sm">
            {([[t("cal.checkFrom"), from, setFrom], [t("cal.checkTo"), to, setTo]] as const).map(([label, value, set]) => (
              <label key={label} className="flex flex-col gap-1">
                {label}
                <select
                  className="rounded-md border border-border bg-transparent p-1"
                  value={value}
                  disabled={!admin}
                  onChange={(e) => set(e.target.value)}
                >
                  <option value="">{t("cal.checkPick")}</option>
                  {parsed.points.map((p) => (
                    <option key={p.point_id} value={p.point_id}>{p.point_id}</option>
                  ))}
                </select>
              </label>
            ))}
            <label className="flex flex-col gap-1">
              {t("cal.checkMeasured")}
              <input
                inputMode="decimal"
                className="w-28 rounded-md border border-border bg-transparent p-1"
                value={measured}
                disabled={!admin}
                onChange={(e) => setMeasured(e.target.value)}
              />
            </label>
          </div>
          {check && (
            <span className={check.ok ? "text-xs" : "error text-xs"}>
              {check.ok
                ? t("cal.checkOk", { computed: m2(check.computed) })
                : t("cal.checkBad", {
                    computed: m2(check.computed),
                    measured: m2(Number(measured)),
                    diff: m2(check.diff),
                    tolerance: m2(check.tolerance),
                  })}
            </span>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={savePoints} disabled={!canSave || busy !== null}>
            {busy === "save" ? t("cal.saving") : t("cal.savePoints")}
          </Button>
          {saved && (
            <>
              <span className="text-sm">{t("cal.pointsSaved", saved)}</span>
              <Button variant="outline" size="sm" onClick={newSet}>{t("cal.newSet")}</Button>
            </>
          )}
        </div>
      </Panel>

      <Panel>
        <span className="stat-label">{t("cal.stepImport")}</span>
        <p className="text-xs text-muted-foreground">{t("cal.importHint")}</p>
        <label className="flex flex-col gap-1 text-sm">
          {t("cal.chooseCsv")}
          <input
            type="file"
            accept=".csv,text/csv"
            disabled={!locked || !admin || busy !== null}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) importFile(f);
              e.target.value = "";
            }}
          />
        </label>
        {imported && (
          <div className="flex flex-col gap-1 text-sm">
            <span>{t("cal.importAccepted", { count: imported.accepted })}</span>
            {imported.rejected_low_inliers.length > 0 && (
              <span className="error">{t("cal.importLow", { ids: imported.rejected_low_inliers.join(", ") })}</span>
            )}
            {imported.unknown_points.length > 0 && (
              <span className="error">{t("cal.importUnknown", { ids: imported.unknown_points.join(", ") })}</span>
            )}
          </div>
        )}
      </Panel>

      <Panel>
        <span className="stat-label">{t("cal.stepResult")}</span>
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={calculate} disabled={!canCalc || busy !== null}>
            {busy === "fit" ? t("cal.calculating") : t("cal.calculate")}
          </Button>
          {!canCalc && admin && why && <span className="text-xs text-muted-foreground">{why}</span>}
        </div>
        {fit && (
          <>
            <dl className="grid grid-cols-[1fr_auto] gap-x-6 gap-y-1 text-sm sm:max-w-md">
              {(
                [
                  ["cal.statScale", fit.stats.scale.toFixed(6)],
                  ["cal.statRefs", fit.stats.reference_points],
                  ["cal.statSpread", fit.stats.point_spread],
                  ["cal.statResidualMedian", m2(fit.stats.residual_median_m)],
                  ["cal.statResidualMax", m2(fit.stats.residual_max_m)],
                  ["cal.statTestCount", fit.stats.test_points],
                  ["cal.statTestMedian", m2(fit.stats.test_median_m)],
                  ["cal.statTestP90", m2(fit.stats.test_p90_m)],
                  ["cal.statTestMax", m2(fit.stats.test_max_m)],
                ] as [TranslationKey, string | number][]
              ).map(([k, v]) => (
                <div key={k} className="contents">
                  <dt className="text-muted-foreground">{t(k)}</dt>
                  <dd className="text-right font-mono">{v}</dd>
                </div>
              ))}
            </dl>
            {fit.stats.test_points === 0 && <p className="text-xs text-[var(--bad-fg)]">{t("cal.noTestPoints")}</p>}
            <span className="text-xs font-semibold">{t("cal.plotTitle")}</span>
            <CalibrationPlot rows={fit.rows} />
            <span className="text-xs font-semibold">{t("cal.tableTitle")}</span>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("cal.colPoint")}</TableHead>
                  <TableHead>{t("cal.colRole")}</TableHead>
                  <TableHead>{t("cal.colMeasuredAt")}</TableHead>
                  <TableHead>{t("cal.colLocalizedAt")}</TableHead>
                  <TableHead>{t("cal.colError")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {fit.rows.map((r) => (
                  <TableRow key={r.point_id}>
                    <TableCell>{r.point_id}</TableCell>
                    <TableCell>{r.role === "reference" ? t("cal.roleReference") : t("cal.roleTest")}</TableCell>
                    <TableCell>{m2(r.x_m)}, {m2(r.y_m)}</TableCell>
                    <TableCell>
                      {r.observed_x === null ? t("cal.noObservation") : `${m2(r.observed_x)}, ${m2(r.observed_y)}`}
                    </TableCell>
                    <TableCell>{m2(r.error_m)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            {admin && (
              <div>
                <Button onClick={() => openDialog({ kind: "apply" })} disabled={busy !== null}>
                  {t("cal.apply")}
                </Button>
              </div>
            )}
          </>
        )}
      </Panel>

      <Panel>
        <span className="stat-label">{t("cal.historyTitle")}</span>
        {history.length === 0 ? (
          <span className="muted text-sm">{t("cal.historyEmpty")}</span>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("cal.colStatus")}</TableHead>
                <TableHead>{t("cal.colSource")}</TableHead>
                <TableHead>{t("cal.colWhen")}</TableHead>
                <TableHead>{t("cal.colScale")}</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {history.map((h) => (
                <TableRow key={h.id}>
                  <TableCell>
                    {h.status === "applied" ? t("cal.statusApplied") : t("cal.statusSuperseded")}
                  </TableCell>
                  <TableCell>{h.source === "fit" ? t("cal.sourceFit") : t("cal.sourceRevert")}</TableCell>
                  <TableCell>{formatDate(h.created_at, locale)}</TableCell>
                  <TableCell className="font-mono">{h.scale.toFixed(6)}</TableCell>
                  <TableCell>
                    {admin && h.status !== "applied" && (
                      <Button size="sm" variant="outline" disabled={busy !== null} onClick={() => openDialog({ kind: "revert", row: h })}>
                        {t("cal.revert")}
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Panel>

      <ApplyAlignmentDialog
        open={open}
        onOpenChange={setOpen}
        title={dialogTitle}
        lines={dialogLines}
        confirmLabel={pending?.kind === "revert" ? t("cal.revert") : t("cal.applyConfirm")}
        busy={busy === "apply"}
        error={dialogError}
        onConfirm={confirm}
      />
    </>
  );
}

export default function CalibrationRoute() {
  // useSearchParams wajib di dalam Suspense pada static export.
  return (
    <Suspense fallback={<p className="muted">...</p>}>
      <CalibrationPage />
    </Suspense>
  );
}
