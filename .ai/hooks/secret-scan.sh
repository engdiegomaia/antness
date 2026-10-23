#!/usr/bin/env bash
# Scans staged files (or given files) for credentials that must never ship in an
# embedded image. Run as a pre-commit hook and in CI.
set -uo pipefail

files=("$@")
if [ ${#files[@]} -eq 0 ]; then
  mapfile -t files < <(git diff --cached --name-only --diff-filter=ACM 2>/dev/null)
fi
[ ${#files[@]} -gt 0 ] || exit 0

status=0
report() { echo "[SECRET] $1"; status=1; }

for f in "${files[@]}"; do
  [ -f "$f" ] || continue
  case "$f" in *.md|*/docs/*) continue ;; esac

  # Key material
  grep -nE 'BEGIN (RSA|EC|OPENSSH|PGP|DSA|ENCRYPTED)? ?PRIVATE KEY' "$f" \
    && report "$f: private key material"

  # Common embedded credential patterns
  grep -niE '^\s*(CONFIG_[A-Z_]*(PSK|PASSWORD|PASSPHRASE|WIFI_PASSWORD)|.*wifi[_-]?pass)\s*=\s*"[^"]{4,}"' "$f" \
    && report "$f: Wi-Fi credential"
  grep -niE '(api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token)\s*[:=]\s*["'"'"'][A-Za-z0-9_\-]{16,}' "$f" \
    && report "$f: API key or token"
  grep -nE 'root:[^*!:]{1,}:' "$f" && report "$f: non-locked root password hash"

  # Yocto / Buildroot specific
  case "$f" in
    *local.conf|*.bb|*.bbappend|*defconfig|*sdkconfig*|*prj.conf)
      grep -nE 'debug-tweaks|allow-empty-password|empty-root-password' "$f" \
        && report "$f: debug image feature — must not reach a production image"
      ;;
  esac

  # Containers
  case "$f" in
    Dockerfile*|*docker-compose*.yml|*.yaml)
      grep -niE '^\s*(ENV|ARG)?\s*[A-Z_]*(PASSWORD|TOKEN|SECRET|KEY)\s*[:=]\s*\S{8,}' "$f" \
        && report "$f: credential in container configuration"
      ;;
  esac
done

if [ $status -ne 0 ]; then
  cat >&2 <<'EOF'

Secrets must never be committed. Deleting the file does NOT remove it from git history.
Treat every finding as compromised: rotate the credential, then remove it from history.
See .ai/rules/shared/40-embedded-security.md.
EOF
fi
exit $status
