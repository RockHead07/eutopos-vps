# Eutopos VPS handoff

## 1. Project Overview & Goal

Markerless indoor positioning for the PENS campus in Surabaya. A self-hosted VPS estimates a phone camera's 6-DoF pose from a single image. Android uses the metric pose to correct local ARCore tracking and guide users to rooms. This is a single-floor MVP in field trials. The floor-10 loop scan registered 401/402 frames and accepted 36/46 queries from another day. Those figures measure registration and acceptance. See [field results](docs/spike-plan.md).

**Snapshot.** The main implementation below is from the locally cached VPS `origin/main` (`9dbafa0`) and sibling `eutopos-mobile` `origin/main` (`31afaec`). The VPS working checkout (`2930dc2`, 27 commits behind) has video ingestion, file-based alignment, manual publish and graph routing. The mobile working checkout (`c93cd08`) uses the graph and lacks the recorder spike. A mobile build from `31afaec` requires a published walkable grid for routes, so pair it with the newer VPS. Git refs were inspected locally. Live deployment was not checked.

## 2. Tech Stack & Repository Structure

- **VPS/build:** Python 3.12, FastAPI/Pydantic, SQLModel/psycopg, Alembic, PostgreSQL 17, PyTorch, hloc, PyCOLMAP, OpenCV, NumPy, h5py and Pillow. Docker Compose runs API, map worker, DB and tusd behind Cloudflare Tunnel/Access.
- **Dashboard:** TypeScript, Next.js static export served by FastAPI, React, Tailwind, shadcn/Radix, Uppy/tus and Plotly. The optional 3D build uses a separate CUDA gsplat worker and PlayCanvas tooling/viewer.
- **Mobile:** Unity 6000.3.14f1, C#, AR Foundation and ARCore XR Plugin 6.3.4, uGUI, Newtonsoft.Json and UnityWebRequest.

```text
eutopos-vps/
  server/          API, persistence, map and splat workers
    migrations/    Alembic
  spike/           Extraction, SfM, inspection, benchmarks
  web/             Dashboard
    app/           Pages
    components/    UI and map editor
  deploy/          Containers and pull deployment
  tests/           Python tests and shared wire fixtures
  docs/            Field results, designs and runbooks
../eutopos-mobile/
  Assets/
    Eutopos/       Scripts, scenes, EditMode tests, recorder spike
  Packages/        Unity dependencies
  ProjectSettings/ Android and XR settings
```

## 3. Capturing App Details

- **Video workflow:** stock phone camera plus browser upload. The runbook calls for landscape, 1× lens, 1080p or 4K at 30 FPS, EIS and HDR off manually. Source codec follows the device. OpenCV retains the sharpest frame per window at ~2 FPS for mapping and ~0.5 FPS for test video, writing JPEG quality 95 at decoded resolution.
- **Recorder spike:** separate APK/scene using AR Foundation `ARCameraManager` and ARCore CPU images. It selects the largest supported configuration with long side ≤1920 when available, then rotates images upright and encodes JPEG quality 90. It takes the first tracked frame, then captures after ≥0.4 m or ≥10° while tracking and moving ≤0.7 m/s. Keyframe FPS varies. The scene enables autofocus and disables image stabilization, with no runtime EIS toggle, focus/exposure lock or raw IMU/gravity stream. `TryGetIntrinsics` supplies K, scaled and rotated to match the JPEG.
- The recorder writes `spike/<session>/images/000001.jpg`, `frames.jsonl`, `configs.json` and `meta.json` under Unity persistent storage. Each JSONL record carries the frame timestamp in ns (0 if unavailable), tracking state and Unity-world left-handed Y-up VIO pose. `configs.json` has `available` and nullable `selected` configurations (`width`, `height`, nullable `fps`). `meta.json` records device/app version, selected configuration, frame and tracking-loss counts, skip reasons and coordinate conventions. [PLANNED] Production Mapper session management, ZIP creation and in-app upload. See mobile `Assets/Eutopos/Spike/`.

```json
{"file":"000001.jpg","t_ns":123456789,"position":[0,0,0],"rotation_xyzw":[0,0,0,1],"tracking":"Tracking","K":{"fx":900,"fy":900,"cx":540,"cy":960,"width":1080,"height":1920}}
```

## 4. Reconstruction & VPS Pipeline

- Job intake creates a PostgreSQL row, then tusd `/files/` receives resumable uploads with string metadata `job_id` and `name`. The worker accepts video, CLI frame directories and, on the newer ref, posed ZIPs (`images/NNNNNN.jpg`, `frames.jsonl` required for mapping, optional `meta.json`/`configs.json`). `server/frame_package.py` validates entries, sizes and frame references. Uploaded originals are removed after extraction or on failure.
- hloc uses ALIKED-N16 (1,024 keypoints, 1,024 px long side), MegaLoc (512 px) for top-20 map retrieval, up to 10 forward sequential neighbors per capture sequence and LightGlue matches. PyCOLMAP runs sparse SfM and serves the largest component. SIFT and NN-ratio are benchmark options. A separate gsplat worker can train from SfM and publish a `.sog` viewer asset.
- `/maps/<area>/job-<id>/` holds versioned COLMAP binaries and local HDF5 features under `kp1024-r1024/`, plus `global-r512.h5` and inspection artifacts. PostgreSQL tracks versions and the active map per area. `EUTOPOS_AREA` selects the one area served by a process. Manual publish hot-loads the map. `EUTOPOS_AUTO_PUBLISH` opts into publishing after the gate (connected map, ≥5 test photos, ≥70% acceptance). For the served area it also waits for alignment.
- Scale is a Sim(3), `p_building = scale * R * p_model + translation`, into right-handed Z-up meters. Survey fit uses ≥4 non-collinear reference points. Newer code also supports one or two known distances and automatically fits registered SfM centers to ≥10 matching ARCore positions when median residual is ≤0.25 m. Applied DB alignment takes precedence over `kp1024-r1024/align.json`. ARCore pose is used after SfM. See `server/alignment.py` and `server/quick_align.py` on `origin/main`.
- `POST /localize` takes multipart `image` (JPEG/PNG, ≤20 MiB) and either all four positive float fields `fx`, `fy`, `cx`, `cy` in upright-image pixels or none. Fallback is same-size map intrinsics, then EXIF/default focal length. MegaLoc dot-product retrieval (top 5), ALIKED/LightGlue, and PyCOLMAP 2D–3D PnP/RANSAC run against resident data, serialized per process. Default acceptance is ≥50 inliers.

The worker's `arcore_pose` alignment record has the following shape. Survey records use `reference_points` and `residual_median_m` and default `method` to `survey`. Known-distance records carry `known_distances` entries (`frame_a`, `frame_b`, `distance_m`, `model_distance`), `gravity_spread_deg` and, for two pairs, `scale_spread_percent`.

```json
{"method":"arcore_pose","meter_from_model":{"scale":1.2,"rotation_xyzw":[0,0,0,1],"translation":[0,0,0]},"phone_height_m":1.3,"matched_frames":20,"residual_median_m":0.1,"residual_max_m":0.2}
```

**JSON wire shapes** (illustrative values). `POST /api/jobs` accepts 1–4 entries, each ≤2 GiB, with at least one `peta` entry. The other role is `uji`. `kind` defaults to `video`. `building_id` defaults to null. The local checkout omits those two fields from its schema.

```json
{"area_id":"floor10","area_name":"Floor 10","building_id":null,"videos":[{"name":"peta.zip","role":"peta","size":12345,"kind":"frames"}]}
```

The 201 response and `GET /api/jobs/{id}` use the same shape. Nullable fields appear as null when unavailable. `summary` is a stage-defined object, `received` counts bytes, and dates are ISO 8601.

```json
{"id":1,"area_id":"floor10","status":"uploading","stage":null,"created_by":"mapper@example.test","videos":[{"name":"peta.zip","role":"peta","kind":"frames","size":12345,"uploaded":false,"recorded_at":null,"received":null,"activity_at":null}],"summary":null,"error":null,"map_version_id":null,"created_at":"2026-11-19T00:00:00Z","started_at":null,"finished_at":null,"has_preview":false,"stalled":false}
```

`/localize` returns HTTP 200 for both `ok` and `failed`. Failed poses are both null. `pose_building` is also null without alignment. Pose rotations are world-from-camera XYZW. `intrinsics_source` is `client`, `map` or `exif`. `area_id` and `map_version` are nullable. `t_s` maps stage names to seconds. HTTP 400/413/422/503 cover invalid input, size, validation and unavailable map respectively.

```json
{"contract_version":1,"status":"ok","inliers":120,"correspondences":300,"intrinsics_source":"client","pose_model":{"position":[0.5,0.25,0.1],"rotation_xyzw":[0,0,0,1]},"pose_building":null,"area_id":"floor10","map_version":4,"t_s":{"prep":0.01,"global":0.1,"retrieval":0.01,"local":0.1,"match":0.6,"pose":0.08,"total":0.9}}
```

`GET /health` returns `status` (`ok` or `no_map`) and the loaded map state. `area_id`, `map_version` and `device` are nullable.

```json
{"status":"ok","area_id":"floor10","map_version":4,"map_images":401,"device":"cpu","aligned":true}
```

## 5. Client Navigation & Rendering

Unity solves yaw plus translation against the ARCore pose sampled with the query frame and places an anchored `BuildingRoot`. Corrections are manual or every 5 s during tracked navigation, with one request in flight and confirmation for recent jumps >3 m. Tracking loss hides guidance until a fresh correction. The minimap shares the ARCore-derived pose. There is no independent tracking fallback.

`GET /navgraph` returns a published per-area graph or file fallback. DB publishes include `revision` and can include `walkable`. The grid uses base64 little-endian packed bits in row-major order. Current mobile snaps to the grid and runs 8-neighbor A* without corner cutting, drawing AR chevrons, a POI pin and minimap. Without a grid it disables destinations. The older checkout projects the user onto a graph edge and runs A* over the graph. Missing `contract_version` on `/localize` and `/navgraph` means version 0. See `tests/fixtures/` on VPS `origin/main`.

```json
{"contract_version":1,"area_id":"floor10","map_version":4,"graph":{"frame":"building","units":"m","nodes":[{"id":"P01","x":0,"y":0.4},{"id":"P02","x":1.5,"y":1.6}],"edges":[["P01","P02"]],"targets":[{"node":"P02","name":"Pintu Lab"}]},"revision":"2026-10-22T06:33:00+00:00","walkable":{"frame":"building","units":"m","cell_m":1,"origin":[0,0],"width":3,"height":2,"bits":"Hw==","targets":[{"id":"R1","name":"Lab","x":0.5,"y":0.5}]}}
```

## 6. Hardware & Deployment Constraints

Scan and navigation target ARCore-capable Android phones (ARM64, project min SDK 25, device-dependent camera modes). The initial runbook uses one phone for map and query. Lab host is an i7-10700K with RTX 3070 (8 GB VRAM), WSL2 Ubuntu 24.04 and NVIDIA Container Toolkit. The institutional CPU-only target is 2 vCPU/~7.8 GB RAM. The map worker needs 20 GiB free on its volumes and 30 GiB on the Windows host when a fresh host reading exists. See [deployment](deploy/README.md) and [compute tiers](docs/spike-plan.md#43-tiga-tingkat-perangkat).

## 7. Current Bottlenecks & Open Questions

- Fast turns, blur, lighting transitions and low-texture corridors can fragment SfM. The 50-frame recorder experiment measured 0.097 m median ARCore↔SfM fit residual. Surveyed holdout accuracy, long-session scale drift and cross-device robustness remain open.
- CPU latency/queueing under concurrent clients and shared-GPU contention during builds need measurement. The publish gate checks registration connectivity and query acceptance. It does not measure metric accuracy or route coverage.
- [PLANNED] Multi-area localization and cross-floor routing, a production Mapper, and integration of GoPro MAX 360 capture. Building metadata already exists on the newer server ref. Localization still uses one configured area and navigation uses a single-floor grid.
