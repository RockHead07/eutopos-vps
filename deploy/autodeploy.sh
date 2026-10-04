#!/usr/bin/env bash
# Pull-based deploy of main to this host (docs/specs/2026-10-04-pull-deploy-design.md).
# Run by eutopos-deploy@<user>.timer every 5 minutes. --dry-run: print every decision, change nothing.
# Log: journalctl -u eutopos-deploy@<user>
set -euo pipefail

REPO_SLUG=RockHead07/eutopos-vps
REQUIRED_CHECKS=("Python lint and format" "Workflow security audit" "Tests (Docker)")
STATE_DIR=${XDG_STATE_HOME:-$HOME/.local/state}/eutopos-deploy
WAIT_TIMEOUT=900 # seconds for the api healthcheck (/health) after a deploy

DRY=0
say() { echo "$*"; }
# Repeats every run while nothing changes: only printed with --dry-run, to keep the journal readable.
note() { if ((DRY)); then echo "$*"; fi; }

# success, pending or failure for commit $1. Network errors and rate limits count as pending.
ci_state() {
	local json
	json=$(curl -fsS --max-time 20 -H "Accept: application/vnd.github+json" \
		"https://api.github.com/repos/$REPO_SLUG/commits/$1/check-runs?per_page=100") || {
		echo pending
		return
	}
	python3 -c '
import json, sys
runs = {r["name"]: r for r in json.load(sys.stdin)["check_runs"]}  # latest run per name
state = "success"
for name in sys.argv[1:]:
    r = runs.get(name)
    if r is None or r["status"] != "completed":
        state = "pending" if state == "success" else state
    elif r["conclusion"] != "success":
        state = "failure"
print(state)
' "${REQUIRED_CHECKS[@]}" <<<"$json"
}

running_jobs() {
	docker compose exec -T db psql -U eutopos -d eutopos -tAc \
		"select count(*) from map_job where status = 'running'"
}

up() { docker compose up -d --wait --wait-timeout "$WAIT_TIMEOUT"; }

main() {
	if [[ ${1:-} == --dry-run ]]; then DRY=1; fi
	cd "$(dirname "$0")/.."
	mkdir -p "$STATE_DIR"
	exec 9>"$STATE_DIR/lock"
	flock -n 9 || {
		say "another run is in progress"
		return 0
	}

	local branch cur new deployed back
	branch=$(git symbolic-ref --short -q HEAD || true)
	if [[ $branch != main ]] || ! git diff --quiet HEAD --; then
		say "skip: checkout is not a clean main (${branch:-detached HEAD}); someone is working by hand"
		return 0
	fi
	git fetch -q origin main
	cur=$(git rev-parse HEAD)
	new=$(git rev-parse origin/main)
	# Compared with what was last deployed, not with the checkout: a "git pull" by hand without a
	# rebuild moves the checkout but leaves the old containers running.
	deployed=$(cat "$STATE_DIR/deployed" 2>/dev/null || true)
	if [[ $new == "$deployed" ]]; then
		note "up to date at ${new:0:7}"
		return 0
	fi
	if [[ $new == "$(cat "$STATE_DIR/bad" 2>/dev/null || true)" ]]; then
		note "skip: ${new:0:7} failed its health check before; waiting for a newer commit"
		return 0
	fi
	if ! git merge-base --is-ancestor HEAD origin/main; then
		say "skip: origin/main ${new:0:7} is not a fast-forward of ${cur:0:7}; deploy by hand"
		return 0
	fi
	case $(ci_state "$new") in
	pending)
		note "wait: CI for ${new:0:7} has not finished"
		return 0
		;;
	failure)
		note "skip: CI failed for ${new:0:7}"
		return 0
		;;
	esac

	local running
	running=$(cd deploy && running_jobs) || {
		say "wait: cannot query map jobs (is the db container up?)"
		return 0
	}
	if ((running > 0)); then
		say "wait: $running map job(s) running; deploying ${new:0:7} would fail them"
		return 0
	fi
	# Rollback target: the last deployed commit, or the checkout when nothing is recorded yet.
	back=${deployed:-$cur}
	if ((DRY)); then
		say "would deploy ${back:0:7} -> ${new:0:7}"
		return 0
	fi

	say "deploying ${back:0:7} -> ${new:0:7}"
	git merge -q --ff-only origin/main
	cd deploy
	if ! docker compose build; then
		say "build failed for ${new:0:7}; back to ${cur:0:7}, containers untouched, retry next run"
		git reset -q --hard "$cur"
		return 1
	fi
	if up; then
		echo "$new" >"$STATE_DIR/deployed"
		say "deployed ${new:0:7}"
		return 0
	fi
	echo "$new" >"$STATE_DIR/bad"
	if [[ $back == "$new" ]]; then
		say "health check failed for ${new:0:7}; no earlier deployed commit to roll back to: the service needs a person"
		return 1
	fi
	say "health check failed for ${new:0:7}; rolling back to ${back:0:7}"
	git reset -q --hard "$back"
	if docker compose build && up; then
		say "rolled back to ${back:0:7}"
	else
		say "ROLLBACK FAILED at ${back:0:7}: the service needs a person"
	fi
	return 1
}

# The whole body is parsed before it runs: git merge replacing this file mid-run cannot change this run.
main "$@"
exit
