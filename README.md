# eutopos-vps

**A local Visual Positioning System for indoor navigation.** A phone sends one camera image, and the
server returns the camera's position and orientation in building coordinates. No QR codes, no
physical markers, and no third-party cloud services.

*eu* (good) + *topos* (place): a good place.

Developed as the localization component of an augmented reality indoor navigation platform for a
campus environment.

## Status

🧪 **Early trial.** The pipeline runs on sample data. Field testing is being prepared.

## Design

- **Pipeline:** [hloc](https://github.com/cvg/Hierarchical-Localization) + ALIKED + [LightGlue](https://github.com/cvg/LightGlue), 3D map from [COLMAP](https://colmap.github.io/)
- **Service:** FastAPI, targeting an on-premise server without a GPU
- **Role:** periodic position correction for ARCore tracking in the Android app

## Documentation

The documents below are written in Indonesian.

| File | Contents |
|---|---|
| [`docs/pa-context.md`](docs/pa-context.md) | Project context: history, supervisor guidance, and decisions |
| [`docs/spike-plan.md`](docs/spike-plan.md) | Single-corridor feasibility test plan and results |
| [`docs/design-notes.md`](docs/design-notes.md) | Coordinate alignment, data model, routing, and evaluation metrics |
| [`docs/research-paper.md`](docs/research-paper.md) | Research references, licenses, and method selection rationale |
| [`docs/ci-cd.md`](docs/ci-cd.md) | Automated checks (CI) and deployment plan |

## License

Copyright (C) 2026 Bagus Insan Pradana

Licensed under the **GNU Affero General Public License v3.0**. See [LICENSE](LICENSE).

Anyone who modifies this software and runs it as a network service must make the source code of
their modified version available to its users.
