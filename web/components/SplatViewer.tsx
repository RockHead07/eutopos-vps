"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import type * as PlayCanvas from "playcanvas";
import { api, areaApi, mb, type Room, type SplatPlacement, type Version } from "@/lib/api";
import { parseCam, camToPlayCanvas, type CamPose } from "@/lib/splatCam";
import { useT } from "@/lib/i18n";
import Link from "@/lib/Link";
import { Button } from "@/components/ui/button";
import { Panel } from "@/components/Panel";
import { PageHead } from "@/lib/PageHead";
import { Icon } from "@/lib/Icon";

// Konstanta terdefinisi
const VERTICAL_FOV_DEG = 41.0; // FOV foto latih
const CAMERA_NEAR_CLIP = 0.05;
const CAMERA_FAR_CLIP = 200.0;
const DEFAULT_ROOM_MARKER_HEIGHT_M = 1.6; // tinggi mata rata-rata untuk data ruangan 2D
const UNALIGNED_FALLBACK_ROTATION: [number, number, number] = [180, 0, 0]; // sementara, ditentukan empiris di Task 3 Step 4

interface SplatViewerProps {
  versionId: number | null;
  camParam: string | null;
}

interface DownloadProgress {
  receivedBytes: number;
  totalBytes: number | null;
}

function checkWebGL2(): boolean {
  if (typeof window === "undefined") return true;
  try {
    const canvas = document.createElement("canvas");
    return !!(window.WebGL2RenderingContext && canvas.getContext("webgl2"));
  } catch {
    return false;
  }
}

export function SplatViewer({ versionId, camParam }: SplatViewerProps) {
  const t = useT();

  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const markersOverlayRef = useRef<HTMLDivElement>(null);

  const [webgl2Supported, setWebgl2Supported] = useState(true);
  const [version, setVersion] = useState<Version | null>(null);
  const [rooms, setRooms] = useState<Room[]>([]);
  const [isAligned, setIsAligned] = useState<boolean | null>(null);
  const [loadingVersion, setLoadingVersion] = useState(true);
  const [versionNotFound, setVersionNotFound] = useState(false);
  const [downloadProgress, setDownloadProgress] = useState<DownloadProgress | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [isReady, setIsReady] = useState(false);
  const [showMarkers, setShowMarkers] = useState(true);
  const [camInvalid, setCamInvalid] = useState(false);
  const [retryNonce, setRetryNonce] = useState(0);

  // App & camera refs for cleanup and reset
  const appRef = useRef<PlayCanvas.Application | null>(null);
  const cameraRef = useRef<PlayCanvas.Entity | null>(null);
  const initialCamPose = useRef<{ pos: [number, number, number]; target: [number, number, number] } | null>(null);
  const orbitTargetRef = useRef<PlayCanvas.Vec3 | null>(null);
  const roomsRef = useRef<Room[]>([]);
  const showMarkersRef = useRef(true);
  const isAlignedRef = useRef(false);

  useEffect(() => {
    roomsRef.current = rooms;
  }, [rooms]);

  useEffect(() => {
    showMarkersRef.current = showMarkers;
  }, [showMarkers]);

  useEffect(() => {
    isAlignedRef.current = isAligned === true;
  }, [isAligned]);

  // 1. Initial WebGL2 check
  useEffect(() => {
    if (!checkWebGL2()) {
      setWebgl2Supported(false);
    }
  }, []);

  // 2. Fetch version metadata and rooms
  useEffect(() => {
    if (versionId === null || isNaN(versionId)) {
      setLoadingVersion(false);
      return;
    }

    let active = true;
    setLoadingVersion(true);
    setVersionNotFound(false);

    api.versions()
      .then(async (list) => {
        if (!active) return;
        const v = list.find((item) => item.id === versionId);
        if (!v) {
          setVersionNotFound(true);
          setLoadingVersion(false);
          return;
        }
        setVersion(v);

        // Fetch area graph to extract rooms
        if (v.area_id) {
          try {
            const graph = await areaApi.graph(v.area_id);
            if (active && graph?.rooms) {
              setRooms(graph.rooms);
            }
          } catch {
            // Area graph without rooms is non-fatal
          }
        }
        setLoadingVersion(false);
      })
      .catch(() => {
        if (!active) return;
        setVersionNotFound(true);
        setLoadingVersion(false);
      });

    return () => {
      active = false;
    };
  }, [versionId]);

  // 3. Engine setup, Splat download, and Render loop
  // D5: Keluarkan t dari dependensi efek agar pergantian bahasa tidak memicu download ulang
  useEffect(() => {
    if (!webgl2Supported || !version || !version.has_splat || loadingVersion || !canvasRef.current || !containerRef.current) {
      return;
    }

    let destroyed = false;
    const abortCtrl = new AbortController();
    let blobUrl: string | null = null;
    let ro: ResizeObserver | null = null;

    setDownloadError(null);
    setDownloadProgress({ receivedBytes: 0, totalBytes: null });
    setIsReady(false);

    // D5: Validasi camParam dan simpan status boolean di state
    let parsedCam: CamPose | null = null;
    if (camParam !== null) {
      parsedCam = parseCam(camParam);
      setCamInvalid(!parsedCam);
    } else {
      setCamInvalid(false);
    }

    const currentVersion = version;

    async function initEngine() {
      try {
        const pc = await import("playcanvas");
        if (destroyed) return;

        const canvas = canvasRef.current;
        const container = containerRef.current;
        if (!canvas || !container) return;

        // Device options: antialias false, maxPixelRatio 2
        const maxPr = Math.min(typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1, 2);
        const app = new pc.Application(canvas, {
          graphicsDeviceOptions: {
            antialias: false,
            maxPixelRatio: maxPr,
          },
        });
        appRef.current = app;

        app.start();
        app.setCanvasFillMode(pc.FILLMODE_NONE);
        app.setCanvasResolution(pc.RESOLUTION_AUTO);

        // ResizeObserver
        ro = new ResizeObserver((entries) => {
          for (const entry of entries) {
            const { width, height } = entry.contentRect;
            if (width > 0 && height > 0 && app.graphicsDevice) {
              app.resizeCanvas(width, height);
            }
          }
        });
        ro.observe(container);

        // Camera Entity
        const camera = new pc.Entity("MainCamera");
        camera.addComponent("camera", {
          clearColor: new pc.Color(0.08, 0.09, 0.12, 1.0),
          fov: VERTICAL_FOV_DEG,
          nearClip: CAMERA_NEAR_CLIP,
          farClip: CAMERA_FAR_CLIP,
        });
        app.root.addChild(camera);
        cameraRef.current = camera;

        // Splat Entity
        const splatEntity = new pc.Entity("SplatEntity");
        app.root.addChild(splatEntity);

        // Fetch placement
        let placement: SplatPlacement | null = null;
        let aligned = false;
        try {
          placement = await api.splatPlacement(currentVersion.id);
          aligned = true;
          setIsAligned(true);
        } catch (err: unknown) {
          const apiErr = err as { status?: number; code?: string };
          if (apiErr?.status === 404 && apiErr?.code === "not_aligned") {
            aligned = false;
            setIsAligned(false);
          } else {
            throw err;
          }
        }

        if (destroyed) return;

        // Apply placement or unaligned fallback
        if (aligned && placement) {
          splatEntity.setLocalPosition(placement.position[0], placement.position[1], placement.position[2]);
          splatEntity.setLocalRotation(
            new pc.Quat(
              placement.rotation_xyzw[0],
              placement.rotation_xyzw[1],
              placement.rotation_xyzw[2],
              placement.rotation_xyzw[3]
            )
          );
          splatEntity.setLocalScale(placement.scale, placement.scale, placement.scale);
        } else {
          splatEntity.setLocalEulerAngles(...UNALIGNED_FALLBACK_ROTATION);
        }

        // Configure Camera Pose
        let initPos: [number, number, number];
        let initTarget: [number, number, number];

        if (parsedCam) {
          const pcCam = camToPlayCanvas(parsedCam);
          initPos = pcCam.position;
          initTarget = pcCam.target;
        } else if (aligned && placement) {
          const [px, py, pz] = placement.position;
          initTarget = [px, py, pz];
          initPos = [px, py + 2.0, pz + 5.0];
        } else {
          initTarget = [0, 0, 0];
          initPos = [0, 2.0, 5.0];
        }

        camera.setPosition(initPos[0], initPos[1], initPos[2]);
        const targetVec = new pc.Vec3(initTarget[0], initTarget[1], initTarget[2]);
        camera.lookAt(targetVec, new pc.Vec3(0, 1, 0));

        orbitTargetRef.current = targetVec.clone();
        initialCamPose.current = { pos: [...initPos], target: [...initTarget] };

        // Setup Minimal Orbit Controls
        let isDragging = false;
        let isPanning = false;
        let lastX = 0;
        let lastY = 0;
        let touchStartDist = 0;
        // D6: Lacak ID pointer aktif untuk mencegah rotasi saat cubitan multi-sentuh
        const activePointers = new Set<number>();

        const onPointerDown = (e: PointerEvent) => {
          activePointers.add(e.pointerId);
          if (e.button === 1 || e.button === 2 || e.shiftKey) {
            isPanning = true;
          } else if (e.button === 0) {
            isDragging = true;
          }
          lastX = e.clientX;
          lastY = e.clientY;
          canvas.setPointerCapture(e.pointerId);
        };

        const onPointerMove = (e: PointerEvent) => {
          if (!isDragging && !isPanning) return;
          const dx = e.clientX - lastX;
          const dy = e.clientY - lastY;
          lastX = e.clientX;
          lastY = e.clientY;

          const target = orbitTargetRef.current;
          if (!target) return;

          const camPos = camera.getPosition();
          const offset = camPos.clone().sub(target);
          let dist = offset.length();
          if (dist < 0.01) dist = 0.01;

          if (isPanning) {
            const factor = dist * 0.0015;
            const rightMove = camera.right.clone().mulScalar(-dx * factor);
            const upMove = camera.up.clone().mulScalar(dy * factor);
            target.add(rightMove).add(upMove);
            camera.setPosition(camera.getPosition().add(rightMove).add(upMove));
          } else if (isDragging) {
            // D6: Abaikan rotasi bila lebih dari satu pointer aktif (cubitan/multi-touch)
            if (activePointers.size > 1) return;

            let azimuth = Math.atan2(offset.x, offset.z);
            let elevation = Math.atan2(offset.y, Math.sqrt(offset.x * offset.x + offset.z * offset.z));

            azimuth -= dx * 0.005;
            elevation += dy * 0.005;
            const maxElev = 1.48; // ~85 deg
            if (elevation > maxElev) elevation = maxElev;
            if (elevation < -maxElev) elevation = -maxElev;

            const cosEl = Math.cos(elevation);
            const newOff = new pc.Vec3(dist * cosEl * Math.sin(azimuth), dist * Math.sin(elevation), dist * cosEl * Math.cos(azimuth));
            camera.setPosition(target.x + newOff.x, target.y + newOff.y, target.z + newOff.z);
            camera.lookAt(target, new pc.Vec3(0, 1, 0));
          }
        };

        const onPointerUp = (e: PointerEvent) => {
          activePointers.delete(e.pointerId);
          if (activePointers.size === 0) {
            isDragging = false;
            isPanning = false;
          }
          try {
            canvas.releasePointerCapture(e.pointerId);
          } catch {}
        };

        const onWheel = (e: WheelEvent) => {
          e.preventDefault();
          const target = orbitTargetRef.current;
          if (!target) return;

          const camPos = camera.getPosition();
          const offset = camPos.clone().sub(target);
          let dist = offset.length();
          const factor = 1 + Math.sign(e.deltaY) * 0.08;
          dist = Math.max(0.2, Math.min(150, dist * factor));

          offset.normalize().mulScalar(dist);
          camera.setPosition(target.x + offset.x, target.y + offset.y, target.z + offset.z);
          camera.lookAt(target, new pc.Vec3(0, 1, 0));
        };

        const onTouchStart = (e: TouchEvent) => {
          if (e.touches.length === 2) {
            const dx = e.touches[0].clientX - e.touches[1].clientX;
            const dy = e.touches[0].clientY - e.touches[1].clientY;
            touchStartDist = Math.hypot(dx, dy);
          }
        };

        const onTouchMove = (e: TouchEvent) => {
          if (e.touches.length === 2 && touchStartDist > 0) {
            const dx = e.touches[0].clientX - e.touches[1].clientX;
            const dy = e.touches[0].clientY - e.touches[1].clientY;
            const dist = Math.hypot(dx, dy);
            const delta = dist - touchStartDist;
            touchStartDist = dist;

            const target = orbitTargetRef.current;
            if (!target) return;

            const camPos = camera.getPosition();
            const offset = camPos.clone().sub(target);
            let curDist = offset.length();
            const factor = 1 - delta * 0.005;
            curDist = Math.max(0.2, Math.min(150, curDist * factor));

            offset.normalize().mulScalar(curDist);
            camera.setPosition(target.x + offset.x, target.y + offset.y, target.z + offset.z);
            camera.lookAt(target, new pc.Vec3(0, 1, 0));
          }
        };

        const onTouchEnd = () => {
          touchStartDist = 0;
        };

        canvas.addEventListener("pointerdown", onPointerDown);
        canvas.addEventListener("pointermove", onPointerMove);
        canvas.addEventListener("pointerup", onPointerUp);
        canvas.addEventListener("pointercancel", onPointerUp);
        canvas.addEventListener("wheel", onWheel, { passive: false });
        canvas.addEventListener("touchstart", onTouchStart, { passive: true });
        canvas.addEventListener("touchmove", onTouchMove, { passive: true });
        canvas.addEventListener("touchend", onTouchEnd, { passive: true });
        canvas.addEventListener("touchcancel", onTouchEnd, { passive: true });

        // Update loop: sync HTML marker positions
        const screenPos = new pc.Vec3();
        const worldPos = new pc.Vec3();
        app.on("update", () => {
          const overlay = markersOverlayRef.current;
          if (!overlay) return;

          const camComp = camera.camera;
          if (!camComp || !isAlignedRef.current || !showMarkersRef.current) {
            overlay.style.display = "none";
            return;
          }

          overlay.style.display = "block";
          const activeRooms = roomsRef.current;
          const childDivs = overlay.children;

          for (let i = 0; i < activeRooms.length; i++) {
            const r = activeRooms[i];
            const div = childDivs[i] as HTMLElement | undefined;
            if (!div) continue;

            // Building (x, y, z) -> PlayCanvas (x, z, -y)
            worldPos.set(r.x, DEFAULT_ROOM_MARKER_HEIGHT_M, -r.y);
            camComp.worldToScreen(worldPos, screenPos);

            if (screenPos.z > 0) {
              div.style.display = "flex";
              div.style.left = `${screenPos.x}px`;
              div.style.top = `${screenPos.y}px`;
            } else {
              div.style.display = "none";
            }
          }
        });

        // 4. Download splat file with streaming progress
        const res = await fetch(`/api/versions/${currentVersion.id}/splat`, {
          credentials: "same-origin",
          signal: abortCtrl.signal,
        });

        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }

        const lenHeader = res.headers.get("content-length");
        const total = lenHeader ? parseInt(lenHeader, 10) : null;
        let received = 0;

        const reader = res.body?.getReader();
        const chunks: Uint8Array[] = [];

        if (reader) {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            if (value) {
              chunks.push(value);
              received += value.length;
              setDownloadProgress({ receivedBytes: received, totalBytes: total });
            }
          }
        } else {
          const blobData = await res.blob();
          chunks.push(new Uint8Array(await blobData.arrayBuffer()));
          received = chunks[0].length;
          setDownloadProgress({ receivedBytes: received, totalBytes: total || received });
        }

        if (destroyed) return;

        const splatBlob = new Blob(chunks as BlobPart[], { type: "application/octet-stream" });
        blobUrl = URL.createObjectURL(splatBlob);

        // Load Asset into PlayCanvas
        const asset = new pc.Asset("splat", "gsplat", { url: blobUrl, filename: "scene.sog" });
        app.assets.add(asset);

        asset.ready(() => {
          if (destroyed) return;
          splatEntity.addComponent("gsplat", { asset });
          setIsReady(true);
        });

        asset.on("error", (err: unknown) => {
          if (destroyed) return;
          setDownloadError(String(err) || "Asset load failed");
        });

        app.assets.load(asset);
      } catch (err: unknown) {
        if (destroyed || abortCtrl.signal.aborted) return;
        setDownloadError((err as Error)?.message || "Failed to load 3D splat");
      }
    }

    initEngine();

    return () => {
      destroyed = true;
      abortCtrl.abort();
      if (ro) ro.disconnect();
      if (blobUrl) URL.revokeObjectURL(blobUrl);
      if (appRef.current) {
        appRef.current.destroy();
        appRef.current = null;
      }
      cameraRef.current = null;
      orbitTargetRef.current = null;
    };
  }, [version, webgl2Supported, loadingVersion, retryNonce, camParam]);

  const handleResetCamera = useCallback(() => {
    if (!cameraRef.current || !initialCamPose.current || !orbitTargetRef.current) return;
    const { pos, target } = initialCamPose.current;
    cameraRef.current.setPosition(pos[0], pos[1], pos[2]);
    orbitTargetRef.current.set(target[0], target[1], target[2]);
    cameraRef.current.lookAt(orbitTargetRef.current, { x: 0, y: 1, z: 0 } as PlayCanvas.Vec3);
  }, []);

  // UI Error / Empty States
  if (!webgl2Supported) {
    return (
      <Panel>
        <div className="space-y-3 p-6 text-center">
          <h2 className="text-lg font-semibold text-destructive">{t("splat.noWebGL2")}</h2>
          <Button asChild variant="outline" className="rounded-full">
            <Link href="/maps">{t("splat.backToMaps")}</Link>
          </Button>
        </div>
      </Panel>
    );
  }

  if (versionId === null || isNaN(versionId)) {
    return (
      <Panel>
        <div className="space-y-3 p-6 text-center">
          <h2 className="text-lg font-semibold text-destructive">{t("splat.missingVersion")}</h2>
          <Button asChild variant="outline" className="rounded-full">
            <Link href="/maps">{t("splat.backToMaps")}</Link>
          </Button>
        </div>
      </Panel>
    );
  }

  if (versionNotFound) {
    return (
      <Panel>
        <div className="space-y-3 p-6 text-center">
          <h2 className="text-lg font-semibold text-destructive">{t("splat.versionNotFound")}</h2>
          <Button asChild variant="outline" className="rounded-full">
            <Link href="/maps">{t("splat.backToMaps")}</Link>
          </Button>
        </div>
      </Panel>
    );
  }

  if (!loadingVersion && version && !version.has_splat) {
    return (
      <Panel>
        <div className="space-y-3 p-6 text-center">
          <h2 className="text-lg font-semibold">{t("splat.noSplat")}</h2>
          <p className="text-xs text-muted-foreground">Area: {version.area_id} (v{version.version})</p>
          <Button asChild variant="outline" className="rounded-full">
            <Link href="/maps">{t("splat.backToMaps")}</Link>
          </Button>
        </div>
      </Panel>
    );
  }

  const areaLabel = version ? `${version.area_id} v${version.version}` : String(versionId ?? "");

  return (
    <div className="flex w-full flex-col gap-4">
      {/* D3: Header terintegrasi dengan PageHead dan flex-wrap tombol */}
      <PageHead
        crumbs={[
          { label: t("nav.mapVersions"), href: "/maps/" },
          { label: areaLabel },
        ]}
        title={t("splat.title")}
        controls={
          <div className="flex flex-wrap items-center gap-2">
            {/* D2: Tombol Mesh tanpa ikon */}
            <Button
              variant="outline"
              size="sm"
              disabled
              className="rounded-full opacity-60"
              title={t("splat.meshUnavailable")}
            >
              {t("splat.meshToggle")} ({t("splat.meshUnavailable")})
            </Button>

            {/* D2: Tombol Marker tanpa ikon */}
            <Button
              variant="outline"
              size="sm"
              className="rounded-full cursor-pointer"
              disabled={!isAligned || rooms.length === 0}
              onClick={() => setShowMarkers((prev) => !prev)}
              title={!isAligned || rooms.length === 0 ? t("splat.noMarkers") : undefined}
            >
              {!isAligned || rooms.length === 0
                ? t("splat.noMarkers")
                : showMarkers
                ? t("splat.hideMarkers")
                : t("splat.showMarkers")}
            </Button>

            {/* D2: Tombol Reset Kamera memakai ikon restore */}
            <Button
              variant="outline"
              size="sm"
              className="rounded-full cursor-pointer"
              onClick={handleResetCamera}
            >
              <Icon name="restore" /> {t("splat.resetCamera")}
            </Button>
          </div>
        }
      >
        {version ? (
          <span>
            {version.area_id} (v{version.version})
          </span>
        ) : null}
      </PageHead>

      {/* D3: Peringatan tanpa penyelarasan dan peringatan cam sebagai baris sendiri */}
      {isAligned === false && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3.5 text-sm text-amber-700 dark:text-amber-400">
          {t("splat.notAlignedWarning")}
        </div>
      )}
      {camInvalid && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3.5 text-sm text-amber-700 dark:text-amber-400">
          {t("splat.invalidCam")}
        </div>
      )}

      {/* D3, D4: Viewport 3D dengan tinggi 70dvh (min-h 320px) dan touch-none */}
      <div
        ref={containerRef}
        className="relative w-full h-[70dvh] min-h-[320px] rounded-xl overflow-hidden bg-black border border-border touch-none"
      >
        <canvas ref={canvasRef} className="h-full w-full block outline-none touch-none" />

        {/* HTML Markers Overlay */}
        <div
          ref={markersOverlayRef}
          className="pointer-events-none absolute inset-0 overflow-hidden"
          style={{ display: isAligned && showMarkers ? "block" : "none" }}
        >
          {rooms.map((room) => (
            <div
              key={room.id}
              className="absolute -translate-x-1/2 -translate-y-full flex-col items-center gap-0.5"
              style={{ display: "none" }}
            >
              <div className="rounded border border-primary/20 bg-background/90 px-2 py-0.5 text-[11px] font-semibold text-foreground shadow-md backdrop-blur">
                {room.name}
              </div>
              <div className="h-2 w-2 rounded-full border border-background bg-primary shadow" />
            </div>
          ))}
        </div>

        {/* D1: Downloading / Preparing Progress Overlay - hanya tampil selama !isReady && !downloadError */}
        {!isReady && !downloadError && (
          <div className="absolute inset-0 z-20 flex flex-col items-center justify-center bg-background/80 p-6 backdrop-blur">
            <div className="w-full max-w-sm rounded-xl border bg-card p-6 text-center shadow-lg">
              {downloadProgress &&
              downloadProgress.totalBytes !== null &&
              downloadProgress.receivedBytes >= downloadProgress.totalBytes ? (
                <div className="space-y-2">
                  <h3 className="text-sm font-semibold">{t("splat.preparing")}</h3>
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                    <div className="h-full w-full bg-primary animate-pulse" />
                  </div>
                </div>
              ) : (
                <div className="space-y-2">
                  <h3 className="text-sm font-semibold">{t("splat.downloading")}</h3>
                  {downloadProgress ? (
                    downloadProgress.totalBytes ? (
                      <div className="space-y-2">
                        <p className="text-xs text-muted-foreground">
                          {t("splat.downloadProgress", {
                            received: mb(downloadProgress.receivedBytes),
                            total: mb(downloadProgress.totalBytes),
                            pct: Math.round((downloadProgress.receivedBytes / downloadProgress.totalBytes) * 100),
                          })}
                        </p>
                        <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                          <div
                            className="h-full bg-primary transition-all duration-200"
                            style={{
                              width: `${Math.min(100, Math.round((downloadProgress.receivedBytes / downloadProgress.totalBytes) * 100))}%`,
                            }}
                          />
                        </div>
                      </div>
                    ) : (
                      <p className="text-xs text-muted-foreground">
                        {t("splat.downloadProgressUnknown", {
                          received: mb(downloadProgress.receivedBytes),
                        })}
                      </p>
                    )
                  ) : null}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Download Error Overlay */}
        {downloadError && (
          <div className="absolute inset-0 z-30 flex flex-col items-center justify-center bg-background/80 p-6 backdrop-blur">
            <div className="w-full max-w-sm rounded-xl border border-destructive/30 bg-card p-6 text-center shadow-lg">
              <h3 className="mb-2 text-sm font-semibold text-destructive">{t("splat.downloadFailed")}</h3>
              <p className="mb-4 text-xs text-muted-foreground">{downloadError}</p>
              <Button
                variant="default"
                size="sm"
                className="rounded-full cursor-pointer"
                onClick={() => setRetryNonce((n) => n + 1)}
              >
                {t("splat.retry")}
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
