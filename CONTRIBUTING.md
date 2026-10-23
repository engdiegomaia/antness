# Contributing

This repository is a **template**: people click "Use this template" and get a working
agentic environment for an embedded project. Every change should be judged by whether
it makes that starting point better.

## What belongs here

| Contribution | Where |
|--------------|-------|
| New ecosystem support (a new RTOS, a new build system) | a new skill in `mcu/skills/` or `linux-embedded/skills/` |
| Hard-won knowledge about an existing ecosystem | the existing `SKILL.md` — especially the "common failure modes" table |
| A review discipline that catches real bugs | an agent in `<track>/agents/` |
| A universal constraint | `shared/rules/` |
| Support for another agent harness | `scripts/sync-agent-configs.sh` + `docs/multi-harness.md` |

## What does not belong here

- Project-specific content. This is the template; your board's quirks go in your
  project's `AGENTS.md`.
- Generated files. `.cursor/rules/`, `.github/copilot-instructions.md`, `.continue/`,
  `.codex/`, `GEMINI.md`, and `.claude/{skills,agents}/` are produced by
  `scripts/sync-agent-configs.sh`. Do not add a root `CLAUDE.md`; it masks native loading
  of `AGENTS.md` in Claude Code.
- Generic coding advice an agent already knows. Content earns its place by being
  specific: a command that works, a failure mode with its cause, a value with its
  datasheet citation.

## Standard for skill content

A skill is read by an agent that is about to act. Write for that reader.

- **Commands must be real.** If you have not run it, do not put it in.
- **Failure modes with causes** beat explanations of how something works. The
  "common failure modes" table is the highest-value part of every skill.
- **Cite the source** for any value that looks arbitrary (errata number, datasheet
  section, binding document).
- Say what **not** to do, and why. "Never edit under `tmp/`" prevents more damage than
  a paragraph about the build directory layout.
- No filler. A skill that is 30% preamble wastes context on every load.

## Workflow

```bash
# 1. Make the change to the canonical source (never to a generated adapter)
$EDITOR mcu/skills/zephyr-development/SKILL.md

# 2. Regenerate adapters and validate
./scripts/sync-agent-configs.sh
./scripts/validate.sh

# 3. Test that the template still produces a working project
./scripts/init-project.sh --non-interactive --name test --track mcu --stack zephyr \
  --out /tmp/template-test && ./scripts/validate.sh /tmp/template-test
```

CI runs all three. A PR that hand-edits a generated file fails on the `git diff` check.

## Commit format

```
<type>(<scope>): <description>
```
Types: `feat fix refactor docs test chore ci skill agent rule`
Scope: the skill, agent, rule, or track touched (`zephyr`, `yocto`, `mcu-rules`, `sync`).

## Adding a skill

```bash
mkdir -p mcu/skills/my-rtos
cat > mcu/skills/my-rtos/SKILL.md <<'SKILL'
---
name: my-rtos              # MUST match the directory name — validate.sh enforces this
description: <one line saying when an agent should load this>
track: mcu
---
SKILL
```
Then add the routing entry to `mcu/AGENTS.md` and the row to `docs/skill-index.md`.

## Adding an agent

A markdown file in `<track>/agents/` with `name` (matching the filename), `description`,
`tools` and `model` frontmatter. Write it as instructions to a reviewer, not as
documentation about reviewing.

## Review

Changes to `shared/rules/10-hardware-safety.md` or `hooks/guard-destructive-hardware.sh`
need a second reviewer. Weakening a safety rule is never a drive-by change.
