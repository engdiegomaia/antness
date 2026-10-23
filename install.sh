#!/usr/bin/env bash
# Install the embedded agentic environment into a target project.
#
#   ./install.sh <target-dir> [--track mcu|linux|both] [--mode copy|link] [--user]
#
# --mode link  (default) symlinks into this repo — updates propagate, best for teams
#              that clone this repo once.
# --mode copy  copies files — self-contained, best for handing a project to someone
#              who does not have this repo.
# --user       also installs the shared rules/agents/skills into ~/.claude for use
#              across every project.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET=""; TRACK="both"; MODE="link"; USER_INSTALL=0

usage() { sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --track) TRACK="$2"; shift 2 ;;
    --mode)  MODE="$2";  shift 2 ;;
    --user)  USER_INSTALL=1; shift ;;
    -h|--help) usage ;;
    -*) echo "unknown option: $1" >&2; usage ;;
    *) TARGET="$1"; shift ;;
  esac
done

[ -n "$TARGET" ] || usage
case "$TRACK" in mcu|linux|both) ;; *) echo "bad --track: $TRACK" >&2; exit 1 ;; esac
case "$MODE"  in copy|link) ;;     *) echo "bad --mode: $MODE"  >&2; exit 1 ;; esac

mkdir -p "$TARGET"
TARGET="$(cd "$TARGET" && pwd)"
[ "$TARGET" != "$SRC" ] || { echo "target must differ from the source repo" >&2; exit 1; }

echo "Installing embedded-agentic"
echo "  source: $SRC"
echo "  target: $TARGET"
echo "  track:  $TRACK    mode: $MODE"
echo

place() {  # place <src-relative> <dst-absolute>
  local s="$SRC/$1" d="$2"
  [ -e "$s" ] || return 0
  mkdir -p "$(dirname "$d")"
  rm -rf "$d"
  if [ "$MODE" = "copy" ]; then cp -r "$s" "$d"; else ln -s "$s" "$d"; fi
}

tracks() {
  case "$TRACK" in
    mcu)   echo shared mcu ;;
    linux) echo shared linux-embedded ;;
    both)  echo shared mcu linux-embedded ;;
  esac
}

# --- project-level content -------------------------------------------------
for t in $(tracks); do
  place "$t" "$TARGET/.agents/$t"
done

# --- Claude Code discovery -------------------------------------------------
mkdir -p "$TARGET/.claude/skills" "$TARGET/.claude/agents"
for t in $(tracks); do
  for d in "$SRC/$t"/skills/*/; do
    [ -d "$d" ] || continue
    place "$t/skills/$(basename "$d")" "$TARGET/.claude/skills/$(basename "$d")"
  done
  for f in "$SRC/$t"/agents/*.md; do
    [ -f "$f" ] || continue
    place "$t/agents/$(basename "$f")" "$TARGET/.claude/agents/$(basename "$f")"
  done
done

# --- hooks + mcp -----------------------------------------------------------
place hooks "$TARGET/.agents/hooks"
place mcp   "$TARGET/.agents/mcp"

# --- AGENTS.md -------------------------------------------------------------
if [ -f "$TARGET/AGENTS.md" ]; then
  echo "  AGENTS.md already exists — not overwritten."
  echo "  Add this line to it:   @.agents/shared/../../AGENTS.md"
else
  {
    cat "$SRC/AGENTS.md"
    echo
    echo "## Project-specific context"
    echo
    echo "> Fill this in. Agents read it before touching hardware."
    echo
    echo '```'
    echo "Target hardware:  "
    echo "Build system:     "
    echo "Build command:    "
    echo "Flash command:    "
    echo "Test command:     "
    echo "Boards available: "
    echo "Recovery path:    "
    echo '```'
  } > "$TARGET/AGENTS.md"
  echo "  AGENTS.md created — fill in the project-specific section."
fi

# --- harness adapters ------------------------------------------------------
( cd "$TARGET" && "$SRC/scripts/sync-agent-configs.sh" >/dev/null 2>&1 ) || {
  # The sync script is repo-relative; for installed projects create the
  # native Gemini and Copilot instruction files directly.
  printf '@AGENTS.md\n' > "$TARGET/GEMINI.md"
  mkdir -p "$TARGET/.github"
  cp "$TARGET/AGENTS.md" "$TARGET/.github/copilot-instructions.md"
}

# --- user-level install ----------------------------------------------------
if [ "$USER_INSTALL" = "1" ]; then
  UD="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
  mkdir -p "$UD/skills" "$UD/agents" "$UD/rules/embedded"
  for d in "$SRC"/shared/skills/*/; do ln -sfn "$d" "$UD/skills/$(basename "$d")"; done
  for f in "$SRC"/shared/agents/*.md; do ln -sfn "$f" "$UD/agents/$(basename "$f")"; done
  ln -sfn "$SRC/shared/rules" "$UD/rules/embedded/rules"
  echo "  user-level install into $UD"
fi

echo
echo "Done."
echo "Next:"
echo "  1. Fill in the project-specific section of $TARGET/AGENTS.md"
echo "  2. Review $TARGET/.agents/hooks/ and wire the ones you want"
echo "  3. Run: $SRC/scripts/validate.sh $TARGET"
