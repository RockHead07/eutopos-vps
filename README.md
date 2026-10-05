# eutopos-vps

**A local Visual Positioning System for indoor navigation.** A phone sends one camera image, and the
server returns the camera's position and orientation. No QR codes, no physical markers, and no
third-party cloud services.

*eu* (good) + *topos* (place): a good place.

Developed as the localization component of an augmented reality indoor navigation platform for a
campus environment.

## Status

🧪 **Field trials on a real corridor.** A map built from one walk-through video of a campus corridor
(401 of 402 frames registered in one connected map) localized 36 of 46 test photos taken on another
day. Metric accuracy against surveyed reference points has **not** been measured yet; that is the next
field test.

What runs today, on a lab PC with a GPU behind Cloudflare Tunnel and Access:

- `POST /localize` and `GET /health` (FastAPI), with map versions per area in PostgreSQL.
- A map build queue: walk-through videos are uploaded from the browser (tus, resumable), and a GPU
  worker extracts frames, builds and inspects the map, and registers a new map version.
- A web dashboard: upload, job status, map quality numbers, a 3D view of each map, and publishing a
  map version so `/localize` switches to it without a restart.

## Design

- **Pipeline:** [hloc](https://github.com/cvg/Hierarchical-Localization) + ALIKED + [LightGlue](https://github.com/cvg/LightGlue), MegaLoc retrieval, 3D map from [COLMAP](https://colmap.github.io/)
- **Service:** FastAPI + PostgreSQL in Docker Compose. Latency is also measured on CPU, because the
  target is an on-premise server without a GPU; the lab GPU is used to build maps.
- **Dashboard:** Next.js static export served by the same FastAPI app
- **Role in the platform:** periodic position correction for ARCore tracking in the Android app, not
  continuous tracking

## Documentation

Most documents below are written in Indonesian.

| File | Contents |
|---|---|
| [`docs/pa-context.md`](docs/pa-context.md) | Project context: history, supervisor guidance, and decisions |
| [`docs/spike-plan.md`](docs/spike-plan.md) | Single-corridor feasibility test plan and results |
| [`docs/field-test-runbook.md`](docs/field-test-runbook.md) | How to record map videos and test photos in the field |
| [`docs/design-notes.md`](docs/design-notes.md) | Coordinate alignment, data model, routing, evaluation metrics, and the API contract |
| [`docs/research-paper.md`](docs/research-paper.md) | Research references, licenses, and method selection rationale |
| [`docs/specs/`](docs/specs/) | Design specifications (capture and map pipeline, web upload and map build) |
| [`docs/plans/`](docs/plans/) | Implementation plans that were executed |
| [`docs/prd/`](docs/prd/) | Product requirements for planned work (360 video support) |
| [`deploy/README.md`](deploy/README.md) | Host setup (WSL2, Docker, GPU) and running the service, uploads, tunnel, dashboard, autostart after boot, and SSH |
| [`docs/ci-cd.md`](docs/ci-cd.md) | Automated checks (CI) and the deployment plan |

## License

Copyright (C) 2026 Bagus Insan Pradana

Licensed under the **GNU Affero General Public License v3.0**. See [LICENSE](LICENSE).

Anyone who modifies this software and runs it as a network service must make the source code of
their modified version available to its users.
