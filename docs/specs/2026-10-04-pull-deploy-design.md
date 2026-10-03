# CI/CD stage 3: pull-based deploy to the PC lab

Status: implemented 2026-10-04 (`deploy/autodeploy.sh`, `deploy/systemd/`), installed by the owner
(`deploy/README.md` section 9).
Depends on stage 1 (`docs/specs/2026-10-03-ci-docker-tests-design.md`): the deploy gate is the CI result.

## 1. Problem

The PC lab runs `main`, but only after someone logs in (SSH or remote desktop), runs `git pull` and
`docker compose up -d --build`, and checks that the service came back. Merged fixes wait for that
session, and nobody checks the result the same way twice.

## 2. Decision

The PC lab **pulls**: a systemd timer in the Ubuntu WSL distro checks `main` every 5 minutes and
deploys a new commit only when CI passed on it.

| Option | Why not |
|---|---|
| GitHub Actions deploys over SSH (push) | GitHub would hold a key into the lab network; a public repository must not have that path in |
| Self-hosted runner on the PC lab | Forbidden on a public repository: any pull request could run code on it |
| Images built by CI and pulled from a registry | The PC lab runs the GPU image (cu130, about 3 GB) that CI does not build; a registry adds credentials and storage for no gain while there is one server |

The PC lab builds its own image from the commit, the same way it is built by hand today.

## 3. Design

`deploy/autodeploy.sh`, run by `eutopos-deploy@<user>.service` (oneshot) from
`eutopos-deploy@<user>.timer` (5 minutes after boot, then every 5 minutes):

1. **One run at a time** (`flock`). A run that finds the lock taken exits.
2. **Refuse an unknown state.** The checkout must be on `main` with no tracked changes. Otherwise log
   and stop: somebody is working on the PC lab by hand.
3. `git fetch origin main`. Nothing new: exit quietly.
4. **Skip a known bad commit.** A commit that failed the health check before is recorded and never
   retried; the next commit on `main` is.
5. **Fast-forward only.** If `origin/main` is not a descendant of the running commit (history
   rewritten), log and stop.
6. **CI gate.** The GitHub API (public, no token) must report `Python lint and format`,
   `Workflow security audit` and `Tests (Docker)` as completed with `success` on that exact commit.
   Pending: try again next run. Failed: log and wait for a newer commit.
7. **Never interrupt a map build.** If a job is `running` (query in the `db` container), wait for the
   next run: restarting the worker marks a running job failed (`server/jobs.py` `recover_stale`).
   Queued jobs are fine; the new worker picks them up.
8. **Deploy:** `git merge --ff-only`, `docker compose build`, then
   `docker compose up -d --wait --wait-timeout 900` (waits for the `api` healthcheck, which calls
   `/health`).
   - **Build fails:** reset the checkout to the previous commit. Containers were not touched. Retried
     next run (a network error is the usual cause).
   - **Health check fails:** record the commit as bad, reset to the previous commit, rebuild and start
     it again (rollback).

Everything is logged to the journal: `journalctl -u eutopos-deploy@<user>`.

The script body is one function called on the last line, so `git merge` replacing the script file
during a run cannot change the run already in progress.

## 4. Limits

- **Database migrations are not rolled back.** `api` runs `alembic upgrade head` on start. If a bad
  commit migrated the schema, the rollback starts older code on a newer schema. Migrations must stay
  backward compatible for one version; otherwise roll back by hand.
- **The unit files themselves are not deployed.** A change under `deploy/systemd/` needs the install
  step again (`sudo`, owner).
- **GitHub API rate limit** for unauthenticated calls is per IP and the campus network may share an IP.
  The API is only called when there is a new commit; a rate-limited answer counts as pending.
- **Deploy history** is the journal only. Showing it in the dashboard is a later step.

## 5. Verification

- `shellcheck` reports nothing on `deploy/autodeploy.sh`.
- On the PC lab, `deploy/autodeploy.sh --dry-run` prints each decision without changing anything:
  up to date; new commit with CI pending; new commit ready.
- After install: a documentation-only commit merged to `main` reaches the PC lab within about 5
  minutes after CI, visible in the journal and in `git log -1` on the PC lab.
