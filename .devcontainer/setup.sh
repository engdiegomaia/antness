#!/usr/bin/env bash
# Host-side tooling for working in this repository. It deliberately does NOT install a
# cross toolchain or an SDK: those are pinned per project and belong in the project's
# own build container (see .ai/rules/shared/20-toolchain-determinism.md).
set -euo pipefail

sudo apt-get update -qq
sudo apt-get install -y -qq --no-install-recommends \
  shellcheck \
  cppcheck \
  clang-format \
  device-tree-compiler \
  picocom \
  minicom \
  usbutils \
  srecord \
  jq

# Serial access without sudo
sudo usermod -aG dialout "$USER" || true

# Install the git pre-commit hook if this is a git checkout
if [ -d .git ] && [ -f .ai/hooks/pre-commit ]; then
  ln -sf ../../.ai/hooks/pre-commit .git/hooks/pre-commit
  echo "pre-commit hook installed"
fi

cat <<'EOF'

Ready.

  ./scripts/init-project.sh      scaffold a project from this template
  ./scripts/validate.sh          check the agent environment
  docs/getting-started.md        walkthrough

Toolchains and SDKs are intentionally not installed here — pin them per project.
EOF
