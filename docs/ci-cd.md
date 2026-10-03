# CI/CD

How this repository is checked automatically, and how the PC lab gets new versions. Claims not yet
verified against a primary source are marked ⚠️.

## 1. Principles

All principles below come from GitHub's
[Secure use reference](https://docs.github.com/en/actions/reference/security/secure-use) for Actions,
unless marked otherwise.

| Principle | How this repo applies it |
|---|---|
| **Actions pinned to a full commit SHA.** The only way to use an action as an immutable release | Every `uses:` is a SHA with the version in a comment. Dependabot updates them |
| **Least-privilege token** | `permissions: {}` at workflow level, `contents: read` per job |
| **No self-hosted runner on a public repository**: anyone can open a pull request that runs code on it | This repo is public. **The PC lab is never a GitHub runner, and GitHub never holds a key to it** (section 4) |
| **No credentials left on the runner** | `persist-credentials: false` on every checkout |
| **Locked tool versions**: CI and laptops run the same versions | uv pinned by `required-version` in `pyproject.toml`; dev tools locked in `uv.lock`; CI uses `--locked` / `--frozen` |
| **Test what ships** (repo decision, `docs/specs/2026-10-03-ci-docker-tests-design.md`) | Unit tests run inside the image built from `deploy/Dockerfile`, the same file the PC lab builds |
| **Every CI command runs locally** | Section 3 |
| **Dependency updates wait a few days** (cooldown) so a bad release can be pulled first | Dependabot `cooldown: 7 days` |

## 2. What runs

`.github/workflows/ci.yml` runs on every pull request, on push to `main`, and manually
(`workflow_dispatch`). A new push to a pull request cancels its older run.

| Job | What it checks | Required for merge |
|---|---|---|
| **Python lint and format** | `ruff check` and `ruff format --check` | yes |
| **Workflow security audit** | [zizmor](https://github.com/zizmorcore/zizmor) on `.github/` (injection, excessive token permissions, unpinned actions) | yes |
| **Tests (Docker)** | Builds `deploy/Dockerfile` up to the `test` target with CPU torch: dependencies, hloc, the Next.js dashboard, then `pytest -q` as the unprivileged `eutopos` user. A failing test fails the build. Nothing is pushed. Layers are cached in the GitHub Actions cache | after it has passed once (section 5) |

The `test` stage is `FROM runtime` plus pytest (version from `uv.lock`) and `tests/`. The service image
is unchanged: `deploy/compose.yaml` builds `target: runtime`, so the PC lab never builds or ships the
tests.

Not covered by CI, on purpose:
- **The GPU image** (cu130, about 3 GB). Runners have no GPU, and the CPU build exercises the same
  Dockerfile apart from the torch index.
- **The six `/localize` tests that need a real map** (`EUTOPOS_MAP_DIR`). Skipped in CI, as on a laptop
  without map data.
- **Timing.** A GitHub runner is not one of the measured targets, so its timings are never results.

`.github/dependabot.yml` opens weekly pull requests for action SHAs and for `uv.lock`, one per
ecosystem.

## 3. Running the same checks locally

```bash
uv sync --inexact             # ruff, zizmor and pytest from uv.lock, WITHOUT removing spike packages
uv run ruff check .
uv run ruff format .          # CI only checks; this rewrites
uv run zizmor .github/
docker build -f deploy/Dockerfile --target test .   # the "Tests (Docker)" job
```

> 🚨 **Do not run `uv sync` without `--inexact` on a laptop with the spike environment.** `uv sync` is
> exact: packages not in `uv.lock` are **removed** from `.venv`
> ([uv docs](https://docs.astral.sh/uv/concepts/projects/sync/)). torch, hloc, pycolmap and LightGlue
> are installed by the Dockerfile (and manually for the spike, `docs/spike-plan.md` section 12), not
> declared in `pyproject.toml`. `uv run` is safe because its sync is inexact.

Changing a tool version: `uv add --dev ruff@<version>` or `uv lock --upgrade-package ruff`, then
commit `pyproject.toml` and `uv.lock` together. **uv itself** is pinned by `required-version`; uv of
another version refuses to run. ⚠️ Not checked whether Dependabot updates that pin: assume it does
not, and bump it by hand (`required-version`, then `uv self update <version>`).

`.claude/` is excluded from ruff: it holds third-party skills copied as they are.

## 4. Delivery to the PC lab

**Pull-based.** The PC lab checks for a new `main` itself, builds, and restarts. GitHub never logs in
to it. Reasons: a public repository must not drive a self-hosted runner, and a server key stored as a
GitHub secret would be a way into the lab network from outside. SSH through the Cloudflare Tunnel
(`deploy/README.md` section 8) is for people, not for deployment.

Design and status: `docs/specs/2026-10-04-pull-deploy-design.md`.

## 5. GitHub settings (owner)

Files in the repo cannot switch these on. In the repository **Settings**:

1. **Ruleset `main-protection`**: pull request required, no bypass, force push blocked, required status
   checks `Python lint and format`, `Workflow security audit`, and **`Tests (Docker)`** (add it after
   the job has passed once: GitHub only offers checks it has seen).
2. **Actions > General**: require actions pinned to a full SHA; default workflow permissions **read**.
3. **Advanced Security**: secret scanning with push protection, Dependabot alerts and security updates,
   code scanning default setup (CodeQL).

Secret scanning only knows credential patterns. **Student ID numbers, internal host names and IP
addresses are not caught.** The public-repo rules in `CLAUDE.md` still need a manual check before
every commit.
