#!/usr/bin/env bash
# Pull agent-environment improvements from the embedded-agentic template into a project
# started from it, without touching project code or the project context in AGENTS.md.
#
#   ./scripts/update-from-upstream.sh [--remote upstream] [--ref main] [--dry-run]
set -euo pipefail

REMOTE="upstream"; REF="main"; DRY=0
UPSTREAM_URL="https://github.com/toradex/embedded-agentic.git"

while [ $# -gt 0 ]; do
  case "$1" in
    --remote) REMOTE="$2"; shift 2 ;;
    --ref) REF="$2"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    -h|--help) sed -n '2,7p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 1 ;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

git rev-parse --git-dir >/dev/null 2>&1 || { echo "not a git repository" >&2; exit 1; }
[ -z "$(git status --porcelain)" ] || { echo "working tree is dirty — commit or stash first" >&2; exit 1; }

if ! git remote get-url "$REMOTE" >/dev/null 2>&1; then
  echo "Adding remote '$REMOTE' -> $UPSTREAM_URL"
  git remote add "$REMOTE" "$UPSTREAM_URL"
fi
git fetch "$REMOTE" "$REF"

# Paths that belong to the environment and are safe to take from upstream.
# AGENTS.md is deliberately excluded: it carries this project's hardware context.
ENV_PATHS=(
  shared/
  mcu/
  linux-embedded/
  hooks/
  scripts/sync-agent-configs.sh
  scripts/validate.sh
  scripts/update-from-upstream.sh
  mcp/
  docs/skill-index.md
  docs/multi-harness.md
  docs/getting-started.md
)

# Only take paths that exist here — a trimmed project has one track.
TAKE=()
for p in "${ENV_PATHS[@]}"; do
  [ -e "${p%/}" ] && TAKE+=("$p")
done

echo
echo "Changes incoming from $REMOTE/$REF:"
git diff --stat "HEAD..$REMOTE/$REF" -- "${TAKE[@]}" || true
echo

if [ $DRY -eq 1 ]; then
  echo "(dry run — nothing changed)"
  exit 0
fi

git checkout "$REMOTE/$REF" -- "${TAKE[@]}"

# AGENTS.md: report upstream rule changes rather than overwriting the project's copy.
echo
echo "AGENTS.md is NOT updated automatically — it holds this project's hardware context."
if ! git diff --quiet "HEAD:AGENTS.md" "$REMOTE/$REF:AGENTS.md" 2>/dev/null; then
  echo "Upstream AGENTS.md changed. Review and merge the environment sections by hand:"
  echo "  git diff HEAD:AGENTS.md $REMOTE/$REF:AGENTS.md"
fi

./scripts/sync-agent-configs.sh >/dev/null
./scripts/validate.sh | tail -3

echo
echo "Staged. Review with 'git diff --cached', then commit:"
echo "  git commit -m 'chore: update agent environment from upstream'"
