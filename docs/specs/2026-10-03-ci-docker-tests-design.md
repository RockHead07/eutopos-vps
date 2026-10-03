# CI stage 1: run the unit tests inside the Docker image

Status: implemented 2026-10-04 (`deploy/Dockerfile` target `test`, job `Tests (Docker)` in
`.github/workflows/ci.yml`). Approved by the owner for implementation on 2026-10-04.
Scope: stage 1 of the CI/CD work. Stage 2 (PC lab autostart and SSH through the Cloudflare Tunnel,
executed by an external agent) and stage 3 (pull-based auto-deploy) get their own documents.

## 1. Problem

- The repo has 84 unit tests (`pytest -q`, 6 more skipped without map data), but CI never runs them.
  A change that breaks the service can be merged into `main` as long as lint passes.
- CI never builds the Docker image. A broken `deploy/Dockerfile` is discovered only when the PC lab
  rebuilds, which today means a manual session over remote desktop.
- The tests import torch, hloc, pycolmap and plotly. torch (from the PyTorch CPU or CUDA index) and
  hloc (pinned to a commit) are installed by the Dockerfile, not declared in `pyproject.toml`, so
  `uv sync && pytest` on a GitHub runner cannot work.

## 2. Decision

Run the tests **inside the image that the PC lab runs**, built from the same Dockerfile.

Alternatives considered:

| Option | Why not |
|---|---|
| Install torch and hloc directly on the runner, plus a separate Docker build job | The torch and hloc install steps would exist twice (Dockerfile and workflow) and drift apart. CI would test a different environment from the server |
| Declare torch and hloc in `pyproject.toml` (the phase 1 plan in `docs/ci-cd.md`) | Correct long term, but selecting CPU vs CUDA wheels through uv touches the Dockerfile, the laptop and the PC lab at once. Too large for this step |

Testing the shipped artifact also proves the Dockerfile builds, including the Next.js dashboard stage.

## 3. Design

### 3.1 Dockerfile

A new stage `test`, after `runtime`:

- `FROM runtime AS test`.
- Install pytest into `/opt/venv` at the version locked in `uv.lock` (`uv export --frozen
  --only-group dev`), using the `uv` binary from the existing `uv` stage.
- Copy `tests/` and `pyproject.toml` (it holds the pytest configuration: `testpaths`, `pythonpath`).
- Run `pytest -q` as the last build step, as the unprivileged `eutopos` user. The build fails when a
  test fails, so CI only needs to build the target.

The `runtime` stage is unchanged. Without a `target`, Docker builds the **last** stage, and today
`deploy/compose.yaml` sets none. So `build.target: runtime` is added to the `api` and `worker`
services in `deploy/compose.yaml` (`compose.gpu.yaml` only overrides `args` and inherits the target).
Otherwise the PC lab would build the test stage, run the tests on every deploy, and ship `tests/`.

`.dockerignore` adds `!tests/`.

### 3.2 Workflow

A new job **`Tests (Docker)`** in `.github/workflows/ci.yml`:

- `runs-on: ubuntu-24.04`, `permissions: contents: read`, `persist-credentials: false`, no secrets.
- Actions pinned to full commit SHAs: `actions/checkout`, `docker/setup-buildx-action`,
  `docker/build-push-action`.
- Build `deploy/Dockerfile` with `target: test`, CPU torch (the Dockerfile default), `push: false`.
- Build cache in the GitHub Actions cache (`type=gha`, `mode=max`) so unchanged layers (torch, hloc,
  npm) are not downloaded on every run.
- `timeout-minutes` set from the measured first run, with margin.

The job **`Dashboard build`** is removed: the image build runs `npm ci` and `next build` in the `web`
stage, so the separate job duplicates it. It is not a required status check today.

### 3.3 Not covered

- The GPU variant (cu130, about 3 GB): GitHub-hosted runners have no GPU and the CPU build already
  exercises the same Dockerfile path apart from the torch index.
- The 6 `/localize` tests that need a real map (`EUTOPOS_MAP_DIR`): they stay skipped in CI, as on a
  laptop without map data.
- Publishing images: nothing is pushed anywhere (stage 3 decides how the PC lab gets new versions).

### 3.4 Repository settings (owner action)

Add `Tests (Docker)` to the required status checks of the `main-protection` ruleset, next to
`Python lint and format` and `Workflow security audit`. This is a security setting of the repository,
so the owner applies it after the job has passed at least once (GitHub only offers checks it has seen).

### 3.5 Documentation

`docs/ci-cd.md` is rewritten in English and brought up to date: it still describes "phase 0" (no unit
tests, no Dockerfile). It records the new job, how to run the same check locally
(`docker build -f deploy/Dockerfile --target test .`), and points to stages 2 and 3.

## 4. Verification

- `uvx zizmor` on `.github/` reports no findings.
- Locally: `docker build --target test` passes with the current tests, and fails when a test is
  broken on purpose (the failure must surface as a failed build, not a silent pass).
- On the pull request: the job is green, its duration is recorded, and a second run shows the cache
  being used (torch and hloc layers reported as cached).
- `docker compose build` on the laptop still produces the `runtime` image (the target change does not
  alter what the PC lab runs).

## 5. Risks

| Risk | Mitigation |
|---|---|
| CI time grows by several minutes per PR | Layer cache; measured on the first run and written in `docs/ci-cd.md` |
| GitHub Actions cache is limited per repository (old entries are evicted) | A cache miss only costs time, never correctness |
| A test needs the network (model download) and turns flaky in CI | Today no test downloads weights; the six real-map tests are skipped. A test that does must be marked and skipped in CI |
