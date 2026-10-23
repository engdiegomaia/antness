#!/usr/bin/env bash
# Install the vendor-neutral .ai harness into an existing project.
#
#   ./install.sh <target-dir> [--track mcu|linux|both] [--mode copy|link] [--user]
#
# --mode link  symlinks into this repository; updates propagate.
# --mode copy  copies the files for a self-contained project.
# --user       also installs shared and selected track sources into ~/.ai.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET=""; TRACK="both"; MODE="link"; USER_INSTALL=0

usage() { sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --track) TRACK="$2"; shift 2 ;;
    --mode) MODE="$2"; shift 2 ;;
    --user) USER_INSTALL=1; shift ;;
    -h|--help) usage ;;
    -*) echo "unknown option: $1" >&2; usage ;;
    *) TARGET="$1"; shift ;;
  esac
done

[ -n "$TARGET" ] || usage
case "$TRACK" in mcu|linux|both) ;; *) echo "bad --track: $TRACK" >&2; exit 1 ;; esac
case "$MODE" in copy|link) ;; *) echo "bad --mode: $MODE" >&2; exit 1 ;; esac

mkdir -p "$TARGET"
TARGET="$(cd "$TARGET" && pwd)"
[ "$TARGET" != "$SRC" ] || { echo "target must differ from the source repo" >&2; exit 1; }

echo "Installing embedded-agentic"
echo "  source: $SRC"
echo "  target: $TARGET"
echo "  track:  $TRACK    mode: $MODE"
echo

place() { # place <src-relative> <dst-absolute>
  local s="$SRC/$1" d="$2"
  [ -e "$s" ] || return 0
  mkdir -p "$(dirname "$d")"
  rm -rf "$d"
  if [ "$MODE" = copy ]; then cp -r "$s" "$d"; else ln -s "$s" "$d"; fi
}

selected_tracks() {
  case "$TRACK" in
    mcu) echo mcu ;;
    linux) echo linux-embedded ;;
    both) echo mcu linux-embedded ;;
  esac
}

# Install the single source tree, selecting only the requested track.
place .ai/README.md "$TARGET/.ai/README.md"
place .ai/roles "$TARGET/.ai/roles"
place .ai/adapters "$TARGET/.ai/adapters"
for scope in shared $(selected_tracks); do
  for category in agents rules skills; do
    place ".ai/$category/$scope" "$TARGET/.ai/$category/$scope"
  done
done
for track in $(selected_tracks); do
  place ".ai/tracks/$track" "$TARGET/.ai/tracks/$track"
done
if [ "$TRACK" != linux ]; then
  place .ai/skills/mcu-tools "$TARGET/.ai/skills/mcu-tools"
  place mcu/tools "$TARGET/mcu/tools"
  place shared/runtime "$TARGET/shared/runtime"
fi

# Hooks and MCP definitions remain executable integration code, not knowledge catalogs.
place .ai/hooks "$TARGET/.ai/hooks"
place .ai/mcp "$TARGET/.ai/mcp"

if [ -f "$TARGET/AGENTS.md" ]; then
  echo "  AGENTS.md already exists — not overwritten."
  echo "  Load the installed harness map at .ai/README.md and relevant .ai/tracks/<track>/AGENTS.md."
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

# The generated files are pointers only; no vendor-specific directories are created.
"$SRC/scripts/sync-agent-configs.sh" "$TARGET" >/dev/null

if [ "$USER_INSTALL" = "1" ]; then
  USER_AI="${AI_CONFIG_DIR:-$HOME/.ai}"
  mkdir -p "$USER_AI"
  for category in agents rules skills; do
    place ".ai/$category/shared" "$USER_AI/$category/shared"
  done
  place .ai/roles "$USER_AI/roles"
  for track in $(selected_tracks); do
    for category in agents rules skills; do
      place ".ai/$category/$track" "$USER_AI/$category/$track"
    done
    place ".ai/tracks/$track" "$USER_AI/tracks/$track"
  done
  echo "  user-level sources installed into $USER_AI"
fi

echo
echo "Done."
echo "Next:"
echo "  1. Fill in the project-specific section of $TARGET/AGENTS.md"
echo "  2. Review $TARGET/.ai/hooks/ and wire the controls supported by your harness"
echo "  3. Run: $SRC/scripts/validate.sh $TARGET"
