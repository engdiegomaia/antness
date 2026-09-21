# Multi-Harness Compatibility

## The model

One canonical file, thin generated adapters.

```
AGENTS.md  (canonical, hand-written)
    |
    +-- CLAUDE.md                        pointer (@AGENTS.md)
    +-- GEMINI.md                        pointer
    +-- .cursor/rules/*.mdc              generated, with Cursor frontmatter
    +-- .github/copilot-instructions.md  generated copy
    +-- .continue/rules/*.md             generated
    +-- .codex/config.toml               execution policy only (Codex reads AGENTS.md natively)
    +-- .agent.md, .rules.md             symlinks for generic AGENTS.md readers
```

Regenerate with `scripts/sync-agent-configs.sh`. Never edit an adapter — the next sync
overwrites it.

## What each harness actually supports

| Capability | Claude Code | Codex | Cursor | Gemini CLI | DeepSeek/generic | Copilot |
|------------|-------------|-------|--------|------------|------------------|---------|
| Instruction file | `CLAUDE.md` | `AGENTS.md` | `.cursor/rules` | `GEMINI.md` | `AGENTS.md` | `.github/copilot-instructions.md` |
| Subagents | native | no | no | no | no | no |
| On-demand skills | native | no | partial (rule globs) | no | no | no |
| Tool-call interception (hooks) | native | limited | no | no | no | no |
| MCP | yes | yes | yes | yes | varies | limited |

## Designing for the lowest common denominator

Because only Claude Code has subagents, skills and hooks, this environment is built so
that **nothing critical depends on them**:

- **Skills** are plain markdown with YAML frontmatter under predictable paths. A harness
  without skill support still reads them when pointed at the file — the root `AGENTS.md`
  routing table tells any agent which file to open.
- **Agents** are plain markdown prompt files. On a harness without subagents, the same
  file is used as a review checklist by the main agent, or pasted as a prompt.
- **Hooks** are standalone shell scripts. Harnesses that cannot intercept tool calls get
  the same protection at the commit boundary via the git `pre-commit` hook and in CI.

This is deliberate: the safety rules must hold whichever agent is driving.

## Per-harness setup

### Claude Code
```bash
./install.sh /path/to/project --track linux
# merge hooks/settings.claude.json into .claude/settings.json
```
Skills and subagents are discovered from `.claude/skills/` and `.claude/agents/`.

### OpenAI Codex
`AGENTS.md` is read natively from the repo root and from subdirectories — the track
`AGENTS.md` files are picked up when working inside `mcu/` or `linux-embedded/`.
Copy `.codex/config.toml` settings into `~/.codex/config.toml`, keeping approval
required for shell commands.

### Cursor
`.cursor/rules/embedded-core.mdc` is `alwaysApply: true`. The per-track rules are
`alwaysApply: false` — reference them with `@mcu` / `@linux-embedded`, or add `globs:`
to the frontmatter so they auto-attach on matching file types:
```yaml
globs: ["**/*.dts", "**/*.bb", "**/*.bbappend"]
```

### Gemini CLI
Reads `GEMINI.md`. The `@AGENTS.md` import is supported; if your version does not
support imports, run the sync script with the content inlined instead of the pointer.

### DeepSeek, Qwen, Cline, Aider, Windsurf and other generic agents
Point them at `AGENTS.md`. The `.agent.md` and `.rules.md` symlinks cover harnesses
that look for those names. For Aider: `aider --read AGENTS.md`.

### GitHub Copilot
`.github/copilot-instructions.md` is applied automatically in VS Code and on
github.com. It is a full copy, so it stays in sync only via the sync script.

## Keeping them in sync

Add to CI:
```yaml
- run: ./scripts/sync-agent-configs.sh
- run: git diff --exit-code   # fails if an adapter was hand-edited or is stale
```
