#!/usr/bin/env bash
# PostToolUse / pre-commit quality gate for embedded sources.
# Runs the right checker for the file type, if it is installed. Never fails the
# session on a missing tool — it reports what it could not check.
#
#   embedded-quality-gate.sh <file> [<file>...]
set -uo pipefail

status=0
skipped=()

have() { command -v "$1" >/dev/null 2>&1; }

check_c() {
  local f="$1"
  if have clang-format && [ -f .clang-format ]; then
    clang-format --dry-run --Werror "$f" 2>&1 | head -20 && true
  else
    skipped+=("clang-format ($f)")
  fi

  # Kernel sources get checkpatch instead of clang-format style
  case "$f" in
    */drivers/*|*/arch/*|*.c)
      if [ -x scripts/checkpatch.pl ]; then
        scripts/checkpatch.pl --no-tree --strict --file "$f" || status=1
      fi ;;
  esac

  if have cppcheck; then
    cppcheck --enable=warning,style --error-exitcode=1 --quiet \
             --suppress=missingIncludeSystem "$f" || status=1
  else
    skipped+=("cppcheck ($f)")
  fi
}

check_dts() {
  local f="$1"
  if have dtc; then
    dtc -I dts -O dtb -o /dev/null "$f" 2>&1 | grep -v "^$" && status=1
  else
    skipped+=("dtc ($f)")
  fi
}

check_bb() {
  local f="$1"
  grep -nE 'SRCREV\s*=\s*"\$\{AUTOREV\}"' "$f" && {
    echo "[FAIL] $f: AUTOREV is forbidden in a shipping recipe"; status=1; }
  grep -nE '^\s*INSANE_SKIP' "$f" && \
    echo "[WARN] $f: INSANE_SKIP present — justify why the QA check does not apply"
  grep -q '^LICENSE' "$f" || { echo "[FAIL] $f: no LICENSE"; status=1; }
}

check_sh() {
  if have shellcheck; then shellcheck "$1" || status=1; else skipped+=("shellcheck ($1)"); fi
}

for f in "$@"; do
  [ -f "$f" ] || continue
  case "$f" in
    *.c|*.h|*.cpp|*.hpp) check_c "$f" ;;
    *.dts|*.dtsi|*.dtso) check_dts "$f" ;;
    *.bb|*.bbappend|*.inc) check_bb "$f" ;;
    *.sh) check_sh "$f" ;;
  esac
done

if [ ${#skipped[@]} -gt 0 ]; then
  printf '[SKIPPED - tool not installed] %s\n' "${skipped[@]}"
fi
exit $status
