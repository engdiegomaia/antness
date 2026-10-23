# Harness source tree

This directory is the single, vendor-neutral source of harness knowledge. Edit these
files directly; do not create mirrored skill, agent, or rule catalogs for individual
tools.

| Path | Contents |
|------|----------|
| agents/shared, agents/mcu, agents/linux-embedded | Specialist and review instructions |
| roles | Engineering role context |
| rules/shared, rules/mcu, rules/linux-embedded | Mandatory engineering constraints |
| skills/shared, skills/mcu, skills/linux-embedded | On-demand domain skills |
| skills/mcu-tools | Usage guidance for executable MCU tools |
| tracks/mcu, tracks/linux-embedded | Track-specific AGENTS.md instructions |
| adapters | Optional harness integration snippets that cannot be represented in AGENTS.md |

The root AGENTS.md remains the universal entrypoint. It routes agents to the relevant
track instructions and the smallest useful set of skills and rules. Executable programs
remain in mcu/tools and shared/runtime. Harness hooks and MCP catalogs live in
.ai/hooks and .ai/mcp.

No .claude, .codex, .cursor, or .continue directories are generated or required. Gemini
and GitHub Copilot receive small pointer files; other tools should read AGENTS.md and
follow its references into .ai.
