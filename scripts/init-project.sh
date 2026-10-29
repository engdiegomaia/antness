#!/usr/bin/env bash
# Turn a fresh clone of this template into a project.
#
#   ./scripts/init-project.sh                          interactive
#   ./scripts/init-project.sh --name my-fw --track mcu --stack zephyr --non-interactive
#
# Options
#   --name <name>        project name (default: the directory name)
#   --track mcu|linux|both
#   --stack <id>         zephyr esp-idf freertos stm32 nuttx
#                        yocto torizon buildroot kernel android
#   --board <name>       target board / module, written into AGENTS.md
#   --keep-all           keep both tracks and every skill (default: trim to the track)
#   --out <dir>          scaffold into <dir> instead of in place
#   --non-interactive    never prompt; fail if a required value is missing
#   --force              proceed even with a dirty or non-git working tree
#
# What it does: writes the project AGENTS.md and README, trims the unused track,
# installs the git pre-commit hook, replaces the template CI with project CI, removes
# template-only files, and regenerates the harness adapters.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAME=""; TRACK=""; STACK=""; BOARD=""; KEEP_ALL=0; OUT=""; INTERACTIVE=1; FORCE=0

usage() { sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --name) NAME="$2"; shift 2 ;;
    --track) TRACK="$2"; shift 2 ;;
    --stack) STACK="$2"; shift 2 ;;
    --board) BOARD="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --keep-all) KEEP_ALL=1; shift ;;
    --non-interactive) INTERACTIVE=0; shift ;;
    --force) FORCE=1; shift ;;
    -h|--help) usage ;;
    *) echo "unknown option: $1" >&2; usage ;;
  esac
done

c_b=$'\033[1m'; c_d=$'\033[2m'; c_g=$'\033[32m'; c_y=$'\033[33m'; c_r=$'\033[31m'; c_0=$'\033[0m'
say()  { printf '%s\n' "$*"; }
step() { printf '%s==>%s %s\n' "$c_b" "$c_0" "$*"; }
ok()   { printf '  %sok%s   %s\n' "$c_g" "$c_0" "$*"; }
warn() { printf '  %swarn%s %s\n' "$c_y" "$c_0" "$*"; }
die()  { printf '%serror:%s %s\n' "$c_r" "$c_0" "$*" >&2; exit 1; }

# --------------------------------------------------------------- stack tables
stack_track() {
  case "$1" in
    zephyr|esp-idf|freertos|stm32|nuttx) echo mcu ;;
    yocto|torizon|buildroot|kernel|android) echo linux ;;
    *) echo "" ;;
  esac
}
stack_skill() {
  case "$1" in
    zephyr)    echo .ai/skills/mcu/zephyr-development ;;
    esp-idf)   echo .ai/skills/mcu/esp-idf-development ;;
    freertos)  echo .ai/skills/mcu/freertos-mcuxpresso ;;
    stm32)     echo .ai/skills/mcu/stm32-hal-development ;;
    nuttx)     echo .ai/skills/mcu/nuttx-development ;;
    yocto)     echo .ai/skills/linux-embedded/yocto-openembedded ;;
    torizon)   echo .ai/skills/linux-embedded/torizon-os ;;
    buildroot) echo .ai/skills/linux-embedded/buildroot-development ;;
    kernel)    echo .ai/skills/linux-embedded/kernel-driver-development ;;
    android)   echo .ai/skills/linux-embedded/android-aosp ;;
  esac
}
stack_build() {
  case "$1" in
    zephyr)    echo 'west build -b <board> app -p auto' ;;
    esp-idf)   echo 'idf.py build' ;;
    freertos)  echo 'cmake -B build -DCMAKE_TOOLCHAIN_FILE=armgcc.cmake && cmake --build build' ;;
    stm32)     echo 'cmake -B build -DCMAKE_TOOLCHAIN_FILE=cmake/gcc-arm-none-eabi.cmake && cmake --build build' ;;
    nuttx)     echo 'cd nuttx && ./tools/configure.sh -l <board>:<config> && make -j$(nproc)' ;;
    yocto)     echo 'kas build kas/project.yml' ;;
    torizon)   echo 'torizoncore-builder build --file tcbuild.yaml' ;;
    buildroot) echo 'make BR2_EXTERNAL=$PWD/br2-external <board>_defconfig && make -j$(nproc)' ;;
    kernel)    echo 'make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j$(nproc)' ;;
    android)   echo 'source build/envsetup.sh && lunch <product>-<release>-<variant> && m -j$(nproc)' ;;
  esac
}
stack_flash() {
  case "$1" in
    zephyr)    echo 'west flash --runner <runner>            # CONFIRM the board first' ;;
    esp-idf)   echo 'idf.py -p /dev/serial/by-id/<stable-id> flash monitor' ;;
    freertos|stm32) echo 'openocd -f interface/<probe>.cfg -f target/<soc>.cfg -c "program build/app.elf verify reset exit"' ;;
    nuttx)     echo 'openocd ... / <vendor tool>             # CONFIRM the board first' ;;
    yocto|buildroot) echo '# Resolve the device by stable id first: lsblk -o NAME,SIZE,MODEL' ;;
    torizon)   echo 'torizoncore-builder deploy --remote-host <ip> --remote-username torizon' ;;
    kernel)    echo 'scp arch/arm64/boot/Image <target>:/boot/  # then reboot' ;;
    android)   echo 'fastboot flashall                        # CONFIRM the device first' ;;
  esac
}
stack_test() {
  case "$1" in
    zephyr)    echo 'west twister -T tests -p native_sim --coverage' ;;
    esp-idf)   echo 'idf.py -T <component> build && pytest --target <target>' ;;
    freertos|stm32|nuttx) echo 'ceedling test:all gcov:all' ;;
    yocto)     echo 'bitbake <image> -c testimage' ;;
    torizon)   echo 'docker compose -f docker-compose.test.yml up --exit-code-from tests' ;;
    buildroot) echo 'make legal-info && <project test runner>' ;;
    kernel)    echo './tools/testing/kunit/kunit.py run --arch=arm64' ;;
    android)   echo 'atest <TestModule>' ;;
  esac
}
stack_build_backend() {
  case "$1" in
    zephyr) echo west ;;
    esp-idf) echo idf ;;
    freertos|stm32) echo cmake ;;
    nuttx) echo nuttx ;;
    *) echo "" ;;
  esac
}
STACKS="zephyr esp-idf freertos stm32 nuttx yocto torizon buildroot kernel android"

# ----------------------------------------------------------------- collect input
DEST="${OUT:-$SRC}"
[ -n "$NAME" ] || NAME="$(basename "$DEST")"

if [ $INTERACTIVE -eq 1 ] && [ -t 0 ]; then
  say
  say "${c_b}antness — project setup${c_0}"
  say "${c_d}Answers go into AGENTS.md, which every agent reads before touching hardware.${c_0}"
  say
  read -r -p "Project name [$NAME]: " a; [ -n "$a" ] && NAME="$a"
  if [ -z "$STACK" ]; then
    say
    say "  MCU:    zephyr  esp-idf  freertos  stm32  nuttx"
    say "  Linux:  yocto  torizon  buildroot  kernel  android"
    while :; do
      read -r -p "Primary stack: " STACK
      [ -n "$(stack_track "$STACK")" ] && break
      say "  ${c_r}unknown stack${c_0} — pick one of: $STACKS"
    done
  fi
  [ -n "$BOARD" ] || read -r -p "Target board / module (e.g. Verdin iMX8MP, nucleo_h743zi): " BOARD
fi

[ -n "$STACK" ] || die "--stack is required (one of: $STACKS)"
[ -n "$(stack_track "$STACK")" ] || die "unknown --stack '$STACK' (one of: $STACKS)"
[ -n "$TRACK" ] || TRACK="$(stack_track "$STACK")"
case "$TRACK" in mcu|linux|both) ;; *) die "--track must be mcu, linux or both" ;; esac
[ -n "$BOARD" ] || BOARD="<fill in>"

# ------------------------------------------------------------------ safety gate
if [ -z "$OUT" ]; then
  if [ $FORCE -eq 0 ]; then
    git -C "$SRC" rev-parse --git-dir >/dev/null 2>&1 \
      || die "not a git repository. Re-run with --force, or --out <dir> to scaffold elsewhere."
    [ -z "$(git -C "$SRC" status --porcelain)" ] \
      || die "working tree is dirty. Commit or stash first, or pass --force."
  fi
  if [ "$(git -C "$SRC" log --oneline 2>/dev/null | wc -l)" -gt 0 ] && [ -f "$SRC/.template-initialized" ]; then
    die "this repository has already been initialized (see .template-initialized)."
  fi
else
  mkdir -p "$DEST"; DEST="$(cd "$DEST" && pwd)"
  [ "$DEST" != "$SRC" ] || die "--out must differ from the template directory"
  step "Copying template into $DEST"
  tar -C "$SRC" --exclude=.git -cf - . | tar -C "$DEST" -xf -
  ok "copied"
fi

TRACK_DIR=""; OTHER_DIR=""
case "$TRACK" in
  mcu)   TRACK_DIR="mcu";            OTHER_DIR="linux-embedded" ;;
  linux) TRACK_DIR="linux-embedded"; OTHER_DIR="mcu" ;;
  both)  TRACK_DIR="mcu linux-embedded" ;;
esac

say
step "Project: ${c_b}$NAME${c_0}   track: $TRACK   stack: $STACK   board: $BOARD"

# ------------------------------------------------------------------ trim tracks
cd "$DEST"
if [ $KEEP_ALL -eq 0 ] && [ -n "$OTHER_DIR" ]; then
  rm -rf ".ai/skills/$OTHER_DIR" ".ai/agents/$OTHER_DIR" ".ai/rules/$OTHER_DIR" ".ai/tracks/$OTHER_DIR"
  if [ "$OTHER_DIR" = mcu ]; then
    rm -rf .ai/skills/mcu-tools mcu/tools
  fi
  ok "removed unused harness track: $OTHER_DIR"
else
  ok "keeping both tracks"
fi

# ------------------------------------------------------------- project AGENTS.md
PRIMARY_SKILL="$(stack_skill "$STACK")"
{
  sed "s|^# AGENTS.md — Antness Development Environment$|# AGENTS.md — $NAME|" AGENTS.md
  cat <<EOF

---

# Project context — $NAME

> **Fill this in before asking an agent to touch hardware.** Most agent failures in
> embedded work are missing-context failures. Everything below is read on every task.

## Hardware

\`\`\`
Target board / module:  $BOARD
Silicon revision:       <rev + the errata document version you work from>
Carrier / baseboard:    <name + revision>
Memory:                 <flash / RAM / eMMC — sizes and regions>
Clock:                  <source -> main clock>
Console:                <UART, baud, /dev/serial/by-id/...>
Debug probe:            <type + serial number>
Recovery path:          <DFU / serial download / JTAG / SD boot / boot switches>
Boards in the lab:      <hostname or serial -> owner>
\`\`\`

## Software

\`\`\`
Primary stack:          $STACK
Primary skill:          $PRIMARY_SKILL
Version / release:      <SDK, Yocto release, kernel version — and where it is pinned>
Toolchain:              <compiler + version, and where it is pinned>
Boot chain:             <ROM -> ... -> application>
Update mechanism:       <none / OTA / RAUC / swupdate / Torizon Cloud / A-B>
\`\`\`

## Commands

\`\`\`bash
# Build (clean tree, one command)
$(stack_build "$STACK")

# Flash / deploy — CONFIRM the target device first
$(stack_flash "$STACK")

# Test
$(stack_test "$STACK")
\`\`\`

## Budgets

\`\`\`
Flash / image size:     <used> / <budget>
RAM:                    <used> / <budget>
Boot time:              <target, per stage>
Power:                  <if battery powered>
\`\`\`

## Project decisions

- Generated files committed: <which, and why>
- Regulated scope: <none / IEC 61508 / IEC 62304 / IEC 62443 / EU CRA / ISO 26262>
- Production hardening: <console disabled, debug features removed, secure boot state>

## Known hazards on this hardware

<Bodge wires, errata workarounds, a rail that must come up before another, a fragile
connector. Anything that would surprise the next person — or agent — to touch it.>
EOF
} > AGENTS.md.new && mv AGENTS.md.new AGENTS.md
ok "AGENTS.md written with the project context section"

# -------------------------------------------------------------- project README
cat > README.md <<EOF
# $NAME

<!-- One paragraph: what this device does and who it is for. -->

Started from the [antness](https://github.com/micron-iot/antness) template.

## Hardware

- **Target:** $BOARD
- **Stack:** $STACK

## Build

\`\`\`bash
$(stack_build "$STACK")
\`\`\`

## Test

\`\`\`bash
$(stack_test "$STACK")
\`\`\`

## Working with AI agents in this repository

\`AGENTS.md\` is the canonical instruction file. Claude Code 2.1.277+, Codex and other
native readers load it directly; generated pointer files serve tools that need another
own entrypoint. **Keep its project-context section current** — it is what stops an agent
from producing confident, wrong answers about this hardware.

Available to agents in this repository:

- Rules in \`.ai/rules/shared/\` — hardware safety, toolchain determinism, testing layers, security
- Skills in \`.ai/skills/<track>/\` — loaded on demand per task
- Review agents in \`.ai/agents/<track>/\` and \`.ai/agents/shared/\`

Irreversible hardware operations (fuse burning, bootloader overwrite, mass erase,
fleet updates) always require explicit human confirmation. See
\`.ai/rules/shared/10-hardware-safety.md\`.

## Repository layout

\`\`\`
AGENTS.md            agent instructions + this project's hardware context
.ai/                 shared and track-specific skills, agents, rules, roles and instructions
mcu/tools/            executable MCU tools, when this project uses the MCU track
.ai/hooks/               destructive-command guard, quality gate, secret scan
docs/                getting started, skill index, multi-harness notes
docs/decisions/      architecture decision records
\`\`\`

## Updating the agent environment

\`\`\`bash
./scripts/update-from-upstream.sh
\`\`\`
EOF
ok "README.md written"

# ------------------------------------------------- machine-readable context
mkdir -p .antness
if [ -f templates/antness/project.json ]; then
  BUILD_BACKEND="$(stack_build_backend "$STACK")"
  python3 "$SRC/scripts/lib/gen_project_config.py" \
      --name "$NAME" --board "$BOARD" --stack "$STACK" \
      --build-backend "$BUILD_BACKEND" \
      --template templates/antness/project.json \
      --out .antness/project.json
  cp templates/antness/local.json.example .antness/local.json.example
  ok ".antness/ created (project.json versioned, local.json.example to copy)"
fi

# ------------------------------------------------------------------ scaffolding
mkdir -p docs/decisions
cat > docs/decisions/0001-record-architecture-decisions.md <<'EOF'
# 1. Record architecture decisions

Date: <today>

## Status
Accepted

## Context
Embedded decisions are expensive to reverse: silicon choice, partition layout, update
mechanism, wire protocol. Two years later nobody remembers why, and the reasoning is
relitigated from scratch — or worse, the constraint is violated because it was invisible.

## Decision
Significant decisions are recorded here as short ADRs: context, options considered,
decision, consequences, and what would make us revisit it.

## Consequences
One more file per decision. In exchange, the next person — or agent — reading the
repository can see the constraints, not just the code.
EOF
ok "docs/decisions/ scaffolded"

# ------------------------------------------------------------- template removals
rm -f .template-initialized
rm -rf .github/ISSUE_TEMPLATE
rm -f .github/PULL_REQUEST_TEMPLATE.md CONTRIBUTING.md
rm -f .github/workflows/template-validate.yml .github/workflows/template-bootstrap.yml .github/TEMPLATE_SETUP.md
rm -f install.sh
rm -rf templates/mcu-project templates/linux-project templates/antness
rm -rf scripts/lib
rmdir templates 2>/dev/null || true
ok "template-only files removed"

# ------------------------------------------------------------------- project CI
mkdir -p .github/workflows
cat > .github/workflows/checks.yml <<'EOF'
name: checks

on:
  push: { branches: [main] }
  pull_request:

jobs:
  agent-environment:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - name: Validate the agent environment
        run: ./scripts/validate.sh
      - name: Adapters are in sync with AGENTS.md
        run: |
          ./scripts/sync-agent-configs.sh
          git diff --exit-code || {
            echo "::error::A generated adapter was hand-edited or is stale."
            echo "Run ./scripts/sync-agent-configs.sh and commit the result."
            exit 1; }

  secrets:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
        with: { fetch-depth: 0 }
      - name: Scan changed files for credentials
        run: |
          base="${{ github.event.pull_request.base.sha || 'HEAD~1' }}"
          files=$(git diff --name-only "$base"...HEAD || true)
          [ -n "$files" ] && ./.ai/hooks/secret-scan.sh $files || echo "no files to scan"

  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
        with: { fetch-depth: 0 }
      - run: sudo apt-get update && sudo apt-get install -y cppcheck device-tree-compiler shellcheck
      - name: Quality gate on changed files
        run: |
          base="${{ github.event.pull_request.base.sha || 'HEAD~1' }}"
          files=$(git diff --name-only "$base"...HEAD || true)
          [ -n "$files" ] && ./.ai/hooks/embedded-quality-gate.sh $files || echo "no files to check"

  # TODO: add the project's own build job.
  # build:
  #   runs-on: ubuntu-latest
  #   container: <the pinned build container for this project>
  #   steps:
  #     - uses: actions/checkout@v5
  #     - run: <the build command from AGENTS.md>
EOF
ok ".github/workflows/checks.yml written"

# ------------------------------------------------------------------- git hooks
if [ -d .git ]; then
  mkdir -p .git/hooks
  ln -sf ../../.ai/hooks/pre-commit .git/hooks/pre-commit
  ok "git pre-commit hook installed"
else
  warn "not a git repository — install the hook after 'git init':"
  warn "  ln -sf ../../.ai/hooks/pre-commit .git/hooks/pre-commit"
fi

# ------------------------------------------------------------------- finalize
./scripts/sync-agent-configs.sh >/dev/null
ok "harness adapters regenerated"

cat > .template-initialized <<EOF
name=$NAME
track=$TRACK
stack=$STACK
board=$BOARD
initialized=$(date -u +%Y-%m-%dT%H:%M:%SZ)
template=antness
EOF

say
./scripts/validate.sh | tail -3
say
say "${c_b}Done.${c_0}"
say
say "Next:"
say "  1. ${c_b}Fill in AGENTS.md and .antness/project.json${c_0}"
say "     ${c_d}Part number, memory map, recovery path, real build command.${c_0}"
say "     ${c_d}This does more for agent output quality than anything else.${c_0}"
say "     ${c_d}cp .antness/local.json.example .antness/local.json${c_0}"
say "     ${c_d}then: python mcu/tools/flow/scripts/flow_cli.py diagnose${c_0}"
say "  2. Read docs/getting-started.md"
say "  3. Track upstream improvements:"
say "     ${c_d}git remote add upstream https://github.com/micron-iot/antness.git${c_0}"
say "  4. Commit:"
say "     ${c_d}git add -A && git commit -m 'chore: initialize $NAME from antness'${c_0}"
say
