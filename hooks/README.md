# Hooks

Harness-agnostic shell scripts. Each works standalone from the command line, from a git
hook, and from a harness hook configuration.

| Script | Purpose | Where to wire it |
|--------|---------|------------------|
| `guard-destructive-hardware.sh` | Blocks fuse burning, mass erase, raw block writes, boot-env changes, fleet pushes | PreToolUse on Bash (Claude Code), or a shell wrapper |
| `embedded-quality-gate.sh` | clang-format / checkpatch / cppcheck / dtc / recipe lint per file type | PostToolUse on edits, pre-commit, CI |
| `secret-scan.sh` | Credentials, private keys, `debug-tweaks`, container secrets | pre-commit, CI, session Stop |
| `pre-commit` | Runs the two above plus a build-artifact reject | `.git/hooks/pre-commit` |

## Claude Code

Merge `settings.claude.json` into the project's `.claude/settings.json`.

## Codex / Cursor / other harnesses

These harnesses do not all support pre-tool interception. Install `pre-commit` as a git
hook and run the scripts in CI — that gives the same protection at the commit boundary
regardless of which agent produced the change.

```bash
ln -sf ../../.agents/hooks/pre-commit .git/hooks/pre-commit
```

## CI

```yaml
- run: .agents/hooks/secret-scan.sh $(git diff --name-only origin/main...HEAD)
- run: .agents/hooks/embedded-quality-gate.sh $(git diff --name-only origin/main...HEAD)
```

## Note on the hardware guard

`guard-destructive-hardware.sh` is a safety net, not the policy. The policy is
`shared/rules/10-hardware-safety.md`, and it applies whether or not the hook is
installed. Pattern matching will always miss cases — an agent that only avoids
destructive operations because a regex caught them is not following the rules.
