# MCP Servers for Embedded Work

`servers.json` is a catalogue, not a configuration. Copy the entries you actually want
into your harness's own config file.

| Harness | File |
|---------|------|
| Claude Code | `.mcp.json` (project) or `~/.claude.json` (user) |
| OpenAI Codex | `~/.codex/config.toml`, `[mcp_servers.<name>]` |
| Cursor | `.cursor/mcp.json` |
| Continue | `config.yaml`, `mcpServers:` |

## Which ones are worth it

**context7** — the highest-value one for this domain. Zephyr, ESP-IDF and kernel APIs
change between releases; a model answering from training data will confidently give you
an API that was removed two LTS versions ago.

**filesystem** scoped at a hardware-docs directory — lets the agent read datasheets,
pinmux tables and errata that cannot live in the repo. This directly addresses the
biggest failure mode in embedded agentic work: missing hardware context.

**git** — useful when the BSP spans several repos and "when did this break" needs blame
across them.

## Serial and device access — read this before enabling

Giving an agent a serial console or a flashing tool means giving it the ability to brick
hardware. If you do it:

- Dedicated development board only. Never a customer or production unit.
- A verified recovery path that does not require rework (USB DFU, serial download, SD boot).
- Read-only first. Add write access deliberately, and keep
  `hooks/guard-destructive-hardware.sh` installed.
- The board is labelled as agent-accessible so nobody else's work lands on it.

The rules in `shared/rules/10-hardware-safety.md` still apply in full. A tool being
available is not authorization to use it.
