#!/usr/bin/env bash
# Validates an embedded-agentic installation: required files, skill frontmatter,
# agent frontmatter, adapter freshness, and hook executability.
#
#   ./validate.sh [target-dir]      (defaults to the repo root)
set -uo pipefail

ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$ROOT" || exit 1

fail=0
ok()   { printf '  \033[32mok\033[0m    %s\n' "$1"; }
bad()  { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; fail=1; }
warn() { printf '  \033[33mwarn\033[0m  %s\n' "$1"; }

echo "Validating $ROOT"
echo
echo "Core files"
for f in AGENTS.md; do
  [ -f "$f" ] && ok "$f" || bad "$f missing"
done
for d in shared/rules shared/roles; do
  [ -d "$d" ] && ok "$d/" || warn "$d/ missing"
done

echo
echo "Skills"
shopt -s nullglob
for s in shared/skills/*/SKILL.md mcu/skills/*/SKILL.md linux-embedded/skills/*/SKILL.md \
         mcu/tools/*/SKILL.md .agents/*/skills/*/SKILL.md .agents/*/tools/*/SKILL.md; do
  dir="$(dirname "$s")"; name="$(basename "$dir")"
  head -1 "$s" | grep -q '^---$' || { bad "$s: no YAML frontmatter"; continue; }
  fm_name="$(sed -n '2,10p' "$s" | grep '^name:' | head -1 | cut -d: -f2- | xargs)"
  grep -q '^description:' "$s" || bad "$s: no description in frontmatter"
  if [ "$fm_name" != "$name" ]; then
    bad "$s: frontmatter name '$fm_name' != directory '$name'"
  else
    ok "skill $name"
  fi
done

echo
echo "Agents"
for a in shared/agents/*.md mcu/agents/*.md linux-embedded/agents/*.md .agents/*/agents/*.md; do
  base="$(basename "$a" .md)"
  head -1 "$a" | grep -q '^---$' || { bad "$a: no YAML frontmatter"; continue; }
  fm_name="$(sed -n '2,12p' "$a" | grep '^name:' | head -1 | cut -d: -f2- | xargs)"
  grep -q '^description:' "$a" || bad "$a: no description"
  grep -q '^tools:' "$a" || warn "$a: no tools list (harness will use defaults)"
  if [ "$fm_name" != "$base" ]; then
    bad "$a: frontmatter name '$fm_name' != filename '$base'"
  else
    ok "agent $base"
  fi
done

echo
echo "Adapters"
if [ -f AGENTS.md ]; then
  if [ -e CLAUDE.md ] || [ -e .claude/CLAUDE.md ] || [ -e CLAUDE.local.md ]; then
    bad "Claude instruction alias masks AGENTS.md; remove it or configure Claude to read both"
  else
    ok "Claude Code can read AGENTS.md directly"
  fi
  for a in GEMINI.md .github/copilot-instructions.md; do
    if [ -e "$a" ]; then
      if [ "$a" -ot AGENTS.md ]; then
        warn "$a is older than AGENTS.md — run scripts/sync-agent-configs.sh"
      else
        ok "$a"
      fi
    else
      warn "$a missing"
    fi
  done
fi

echo
echo "Broken symlinks"
broken="$(find . -type l ! -exec test -e {} \; -print 2>/dev/null)"
if [ -n "$broken" ]; then
  echo "$broken" | while read -r l; do bad "dangling symlink: $l"; done
  fail=1
else
  ok "none"
fi

echo
echo "Executable tools"
if [ -d mcu/tools ] || [ -d .agents/mcu/tools ]; then
  runtime="$(ls -d shared/runtime .agents/shared/runtime 2>/dev/null | head -1)"
  if [ -n "$runtime" ]; then
    if PYTHONPATH="$runtime" python3 -c "import embedded_agentic" 2>/dev/null; then
      ok "runtime package imports"
    else
      bad "shared/runtime/embedded_agentic does not import"
    fi
  else
    bad "mcu/tools present but shared/runtime is missing"
  fi

  for cli in mcu/tools/*/scripts/*_cli.py .agents/mcu/tools/*/scripts/*_cli.py; do
    [ -f "$cli" ] || continue
    name="$(basename "$cli")"
    if ! python3 -c "import ast,sys; ast.parse(open(sys.argv[1]).read())" "$cli" 2>/dev/null; then
      bad "$cli: syntax error"; continue
    fi
    if python3 "$cli" --help >/dev/null 2>&1; then
      ok "$name --help"
    else
      bad "$cli: --help failed (it must work without any hardware attached)"
    fi
    [ -x "$cli" ] || warn "$cli is not executable"
  done
else
  warn "no executable tools installed (linux-only install?)"
fi

echo
echo "JSON files"
json_bad=0
for j in $(find . -name '*.json' -not -path './.git/*' -not -path '*/node_modules/*' 2>/dev/null); do
  case "$j" in *local.json) continue ;; esac
  python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$j" 2>/dev/null || {
    bad "$j is not valid JSON"; json_bad=1; }
done
[ $json_bad -eq 0 ] && ok "all JSON parses"

echo
echo "Hooks"
for h in hooks/*.sh hooks/pre-commit .agents/hooks/*.sh; do
  [ -e "$h" ] || continue
  [ -x "$h" ] && ok "$(basename "$h") executable" || bad "$h not executable"
  bash -n "$h" 2>/dev/null || bad "$h has a syntax error"
done

echo
echo "Runtime tests"
if [ -d tests ]; then
  if python3 -m unittest discover -s tests -q >/tmp/ea-tests.$$ 2>&1; then
    ok "runtime test suite passes"
  else
    bad "runtime test suite fails:"
    sed 's/^/      /' /tmp/ea-tests.$$
  fi
  rm -f /tmp/ea-tests.$$
else
  # Scaffolded projects do not carry the template's own test suite.
  ok "no runtime test suite in this checkout (expected in a scaffolded project)"
fi

echo
echo "Offline agent workflow evaluations"
if [ -f evals/test_implementation_gate.py ]; then
  if python3 -m unittest discover -s evals -q >/tmp/ea-evals.$$ 2>&1; then
    ok "implementation gate evaluations pass"
  else
    bad "implementation gate evaluations fail:"
    sed 's/^/      /' /tmp/ea-evals.$$
  fi
  rm -f /tmp/ea-evals.$$
else
  warn "offline workflow evaluations are not installed"
fi

echo
echo "Config layer hygiene"
if [ -d .embedded-agentic ]; then
  findings="$(python3 -c "
import sys, pathlib
sys.path.insert(0, 'shared/runtime')
from embedded_agentic import config
print('\n'.join(config.lint_layers(pathlib.Path('.'))))
" 2>/dev/null)"
  if [ -n "$findings" ]; then
    echo "$findings" | while read -r line; do [ -n "$line" ] && warn "$line"; done
  else
    ok "project.json / local.json stay in their own scope"
  fi
fi

echo
echo "Project context"
if grep -q "Target hardware:\s*$" AGENTS.md 2>/dev/null; then
  warn "AGENTS.md project-specific section is not filled in — agents will lack hardware context"
fi

echo
if [ $fail -eq 0 ]; then
  echo "PASS"
else
  echo "FAIL — fix the items above"
fi
exit $fail
