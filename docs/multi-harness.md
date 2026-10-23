# Multi-harness compatibility

## One canonical source

AGENTS.md is the repository entrypoint. The vendor-neutral harness source tree is .ai/:

- .ai/skills/<scope>/<name>/SKILL.md contains on-demand workflows and domain knowledge.
- .ai/agents/<scope>/ contains specialist and review instructions.
- .ai/rules/<scope>/ contains required engineering constraints.
- .ai/roles/ contains role context.
- .ai/tracks/<track>/AGENTS.md contains MCU or Embedded Linux guidance.
- .ai/adapters/ contains optional integration snippets that cannot be expressed in AGENTS.md.

Do not duplicate these sources into tool-specific directories. Skills and agents are
plain Markdown; a harness can load the referenced file when it lacks native discovery.
Executable guardrails remain in tools, hooks, pre-commit and CI.

## Entry points

| Harness | Entry point | Setup |
|---------|-------------|-------|
| Claude Code | AGENTS.md | Read AGENTS.md and follow its .ai/ references. Configure tool hooks in the local environment if desired. |
| OpenAI Codex | AGENTS.md | Native repository instructions; use the normal approval controls for shell actions. |
| Cursor | AGENTS.md | Point project instructions at AGENTS.md and follow .ai/ references. |
| Gemini CLI | GEMINI.md | Generated pointer that imports AGENTS.md. |
| GitHub Copilot | .github/copilot-instructions.md | Generated short pointer to AGENTS.md and .ai/. |
| Continue | AGENTS.md | Configure the workspace instruction entrypoint to AGENTS.md. |
| Generic agents | AGENTS.md | Load AGENTS.md, then the selected track and skill files. |

The repository intentionally has no .claude, .codex, .cursor, or .continue directories.
No skills, agents, or rules are generated per vendor. GEMINI.md and the Copilot file are
small pointers only; regenerate them with scripts/sync-agent-configs.sh.

## Task loading sequence

1. Read the root AGENTS.md.
2. Identify the MCU or Embedded Linux track from repository evidence.
3. Load .ai/rules/shared/ and .ai/tracks/<track>/AGENTS.md.
4. Load only the task-matching skill and any directly relevant specialist agent.
5. Use hooks and executable tools for safety-critical command enforcement; do not rely on
   prompts as the only control.

## Local integration

Harnesses can use their own local settings to load AGENTS.md, invoke hooks, or provide
subagent behavior. Keep those settings outside this repository or in a local ignored
configuration. Do not commit vendor-specific config directories. Optional examples that
must be versioned belong under .ai/adapters/ and must not duplicate the canonical rules.

For Aider, a typical entrypoint is to read AGENTS.md. Other generic tools should be
configured to read the same file before acting.

## Keeping pointers in sync

Run:

```bash
./scripts/sync-agent-configs.sh
```

CI verifies the generated pointer files are current and rejects vendor-specific
configuration directories in the repository.
