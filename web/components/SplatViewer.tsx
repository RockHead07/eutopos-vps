"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import type * as PlayCanvas from "playcanvas";
import type { CameraControls } from "playcanvas/scripts/esm/camera-controls.mjs";
import { api, areaApi, mb, type Room, type SplatPlacement, type Version } from "@/lib/api";
import { parseCam, camToPlayCanvas, type CamPose } from "@/lib/splatCam";
import { buildingToPlayCanvas, getBuildingCameraMatrix } from "@/lib/splatAxes";
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
const UNALIGNED_FALLBACK_ROTATION: [number, number, number] = [180, 0, 0];

// Konstanta kontrol kamera PlayCanvas (skala meter)
const DEFAULT_FOCUS_DISTANCE_M = 2.0;
const CAMERA_ZOOM_MIN_M = 0.2;
const CAMERA_ZOOM_MAX_M = 150.0;
const CAMERA_PITCH_MIN_DEG = -90.0;
const CAMERA_PITCH_MAX_DEG = 90.0;
const CAMERA_MOVE_SPEED_MPS = 3.0;
const CAMERA_MOVE_FAST_SPEED_MPS = 8.0;
const CAMERA_MOVE_SLOW_SPEED_MPS = 1.0;

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
  const [showGrid, setShowGrid] = useState(true);
  const [camInvalid, setCamInvalid] = useState(false);
  const [retryNonce, setRetryNonce] = useState(0);

  // App, camera, controls, dan ViewCube refs
  const appRef = useRef<PlayCanvas.Application | null>(null);
  const cameraRef = useRef<PlayCanvas.Entity | null>(null);
  const controlsRef = useRef<CameraControls | null>(null);
  const viewCubeRef = useRef<PlayCanvas.ViewCube | null>(null);
  const gridEntityRef = useRef<PlayCanvas.Entity | null>(null);
  const initialCamPose = useRef<{ focus: PlayCanvas.Vec3; position: PlayCanvas.Vec3 } | null>(null);

  const roomsRef = useRef<Room[]>([]);
  const showMarkersRef = useRef(true);
  const showGridRef = useRef(true);
  const isAlignedRef = useRef(false);

  useEffect(() => {
    roomsRef.current = rooms;
  }, [rooms]);

  useEffect(() => {
    showMarkersRef.current = showMarkers;
  }, [showMarkers]);

  useEffect(() => {
    showGridRef.current = showGrid;
    if (gridEntityRef.current) {
      gridEntityRef.current.enabled = showGrid && isAlignedRef.current;
    }
  }, [showGrid]);

  useEffect(() => {
    isAlignedRef.current = isAligned === true;
    if (gridEntityRef.current) {
      gridEntityRef.current.enabled = isAligned === true && showGridRef.current;
    }
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

  // 3. Engine setup, Splat download, CameraControls, ViewCube, Grid, and Render loop
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

    // Validasi camParam dan simpan status boolean di state
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
        const [pc, { CameraControls }, { Grid }] = await Promise.all([
          import("playcanvas"),
          import("playcanvas/scripts/esm/camera-controls.mjs"),
          import("playcanvas/scripts/esm/grid.mjs"),
        ]);
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

        // Configure Camera Initial Pose
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

        // Set position and orientation BEFORE attaching CameraControls script
        camera.setPosition(initPos[0], initPos[1], initPos[2]);
        const targetVec = new pc.Vec3(initTarget[0], initTarget[1], initTarget[2]);
        camera.lookAt(targetVec, new pc.Vec3(0, 1, 0));

        // focusPoint: posisi + arah depan * 2.0 m untuk cam=; targetVec untuk non-cam
        const initialFocus = parsedCam
          ? camera.getPosition().clone().add(camera.forward.clone().mulScalar(DEFAULT_FOCUS_DISTANCE_M))
          : targetVec.clone();
        const initialPosition = camera.getPosition().clone();

        initialCamPose.current = {
          focus: initialFocus.clone(),
          position: initialPosition.clone(),
        };

        // Attach CameraControls script to camera entity
        camera.addComponent("script");
        const scriptComp = camera.script;
        if (!scriptComp) throw new Error("Failed to add script component to camera");

        const controls = scriptComp.create(CameraControls, {
          properties: {
            focusPoint: initialFocus,
            zoomRange: new pc.Vec2(CAMERA_ZOOM_MIN_M, CAMERA_ZOOM_MAX_M),
            pitchRange: new pc.Vec2(CAMERA_PITCH_MIN_DEG, CAMERA_PITCH_MAX_DEG),
            moveSpeed: CAMERA_MOVE_SPEED_MPS,
            moveFastSpeed: CAMERA_MOVE_FAST_SPEED_MPS,
            moveSlowSpeed: CAMERA_MOVE_SLOW_SPEED_MPS,
          },
        }) as CameraControls;

        controls.focusPoint = initialFocus;
        controls.zoomRange = new pc.Vec2(CAMERA_ZOOM_MIN_M, CAMERA_ZOOM_MAX_M);
        controls.pitchRange = new pc.Vec2(CAMERA_PITCH_MIN_DEG, CAMERA_PITCH_MAX_DEG);
        controls.moveSpeed = CAMERA_MOVE_SPEED_MPS;
        controls.moveFastSpeed = CAMERA_MOVE_FAST_SPEED_MPS;
        controls.moveSlowSpeed = CAMERA_MOVE_SLOW_SPEED_MPS;

        controlsRef.current = controls;

        // ViewCube setup
        const viewCube = new pc.ViewCube(new pc.Vec4(1, 1, 0, 0));
        viewCubeRef.current = viewCube;

        // Pindahkan viewCube.dom dari document.body ke dalam kontainer viewport
        if (viewCube.dom && container) {
          container.appendChild(viewCube.dom);
          viewCube.dom.addEventListener("pointerdown", (e) => e.stopPropagation());
          viewCube.dom.addEventListener("pointerup", (e) => e.stopPropagation());
          viewCube.dom.addEventListener("click", (e) => e.stopPropagation());
        }

        // Tangani event klik muka kubus: EVENT_CAMERAALIGN
        viewCube.on(pc.ViewCube.EVENT_CAMERAALIGN, (axisBuilding: PlayCanvas.Vec3) => {
          if (!controlsRef.current || !cameraRef.current) return;

          // Ubah sumbu kerangka gedung ke PlayCanvas: (vx, vy, vz) -> (vx, vz, -vy)
          const axisPC = buildingToPlayCanvas(axisBuilding);

          const focus = controlsRef.current.focusPoint.clone();
          const currentPos = cameraRef.current.getPosition();
          const dist = Math.max(currentPos.distance(focus), 0.5);

          // Penanganan degenerasi lookAt untuk pandangan atas (+Z gedung) dan bawah (-Z gedung):
          // Tambahkan epsilon kecil pada sumbu Z (1e-4) agar arah depan tidak persis sejajar sumbu Y dunia,
          // mencegah NaN dan menjaga roll bernilai 0 dengan arah Utara (gedung +Y) menghadap atas layar.
          if (Math.abs(axisPC.y) > 0.999) {
            axisPC.z += 1e-4 * Math.sign(axisPC.y);
            axisPC.normalize();
          }

          const targetPos = focus.clone().add(axisPC.mulScalar(dist));
          controlsRef.current.reset(focus, targetPos);
        });

        // Floor Grid setup (opsional)
        try {
          const gridEntity = new pc.Entity("GridFloor");
          gridEntity.setLocalScale(100, 1, 100);
          gridEntity.addComponent("script");
          const gridScript = gridEntity.script;
          if (gridScript) {
            gridScript.create(Grid, {
              properties: {
                resolution: Grid.RESOLUTION_HIGH,
              },
            });
          }
          app.root.addChild(gridEntity);
          gridEntity.enabled = aligned && showGridRef.current;
          gridEntityRef.current = gridEntity;
        } catch (gridErr) {
          console.warn("Failed to initialize floor Grid:", gridErr);
        }

        // Update loop
        const mPrime = new pc.Mat4();
        const screenPos = new pc.Vec3();
        const worldPos = new pc.Vec3();

        app.on("update", () => {
          // Update ViewCube dengan matriks M' = P^-1 * W
          if (viewCubeRef.current && cameraRef.current) {
            getBuildingCameraMatrix(cameraRef.current.getWorldTransform(), mPrime);
            viewCubeRef.current.update(mPrime);
          }

          // Sinkronisasi posisi marker HTML ruangan
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

            // Gedung (x, y, z) -> PlayCanvas (x, z, -y)
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
      if (viewCubeRef.current) {
        viewCubeRef.current.destroy();
        viewCubeRef.current = null;
      }
      if (gridEntityRef.current) {
        gridEntityRef.current.destroy();
        gridEntityRef.current = null;
      }
      if (appRef.current) {
        appRef.current.destroy();
        appRef.current = null;
      }
      controlsRef.current = null;
      cameraRef.current = null;
    };
  }, [version, webgl2Supported, loadingVersion, retryNonce, camParam]);

  const handleResetCamera = useCallback(() => {
    if (!controlsRef.current || !initialCamPose.current) return;
    const { focus, position } = initialCamPose.current;
    controlsRef.current.reset(focus, position);
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
      {/* Header dengan PageHead dan flex-wrap tombol kontrol */}
      <PageHead
        crumbs={[
          { label: t("nav.mapVersions"), href: "/maps/" },
          { label: areaLabel },
        ]}
        title={t("splat.title")}
        controls={
          <div className="flex flex-wrap items-center gap-2">
            {/* Tombol Grid (opsional) */}
            <Button
              variant="outline"
              size="sm"
              className="rounded-full cursor-pointer"
              disabled={!isAligned}
              onClick={() => {
                setShowGrid((prev) => {
                  const next = !prev;
                  if (gridEntityRef.current) {
                    gridEntityRef.current.enabled = next && isAlignedRef.current;
                  }
                  return next;
                });
              }}
            >
              {t("splat.gridToggle")}
            </Button>

            {/* Tombol Mesh tanpa ikon */}
            <Button
              variant="outline"
              size="sm"
              disabled
              className="rounded-full opacity-60"
              title={t("splat.meshUnavailable")}
            >
              {t("splat.meshToggle")} ({t("splat.meshUnavailable")})
            </Button>

            {/* Tombol Marker tanpa ikon */}
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

            {/* Tombol Reset Kamera memakai ikon restore */}
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

      {/* Peringatan tanpa penyelarasan dan peringatan cam sebagai baris sendiri */}
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

      {/* Viewport 3D dengan tinggi 70dvh (min-h 320px) dan touch-none */}
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

        {/* Downloading / Preparing Progress Overlay - hanya tampil selama !isReady && !downloadError */}
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

      {/* Bantuan Navigasi & Kontrol (<details>) */}
      <details className="rounded-xl border border-border bg-card p-3.5 text-xs text-muted-foreground transition-all">
        <summary className="cursor-pointer font-medium text-foreground select-none">
          {t("splat.controls.title")}
        </summary>
        <ul className="mt-2.5 space-y-1.5 border-t border-border/50 pt-2.5">
          <li>{t("splat.controls.orbit")}</li>
          <li>{t("splat.controls.pan")}</li>
          <li>{t("splat.controls.zoom")}</li>
          <li>{t("splat.controls.fly")}</li>
          <li>{t("splat.controls.keys")}</li>
          <li>{t("splat.controls.speed")}</li>
          <li>{t("splat.controls.viewcube")}</li>
        </ul>
      </details>
    </div>
  );
}
