# Getting Started

Two ways in: start a new project **from** the template, or add the environment **to** an
existing project.

---

## A. New project from the template

### 1. Create the repository

On GitHub: **Use this template → Create a new repository**.

Or from the CLI:
```bash
gh repo create my-project --template toradex/embedded-agentic --private --clone
cd my-project
```

### 2. Scaffold

```bash
./scripts/init-project.sh
```

Interactive; it asks for the project name, stack and board. Non-interactive:

```bash
./scripts/init-project.sh --non-interactive \
  --name thermal-gateway --stack torizon --board "Verdin iMX8MP Quad 4GB WB IT"
```

| Flag | Meaning |
|------|---------|
| `--stack` | `zephyr esp-idf freertos stm32 nuttx yocto torizon buildroot kernel android` |
| `--track` | inferred from the stack; override with `mcu`, `linux` or `both` |
| `--board` | target board/module, written into `AGENTS.md` |
| `--keep-all` | keep both tracks and every skill instead of trimming |
| `--out <dir>` | scaffold into another directory instead of in place |
| `--force` | proceed on a dirty or non-git tree |

What it does:

- writes `AGENTS.md` — the canonical rules plus a **Project context** section prefilled
  with your stack's build, flash and test commands
- writes a project `README.md`
- removes the unused track so agents do not load irrelevant context
- scaffolds `docs/decisions/` for architecture decision records
- installs the git `pre-commit` hook
- replaces the template CI with project CI (`.github/workflows/checks.yml`)
- removes template-only files and regenerates every harness adapter

It refuses to run twice (`.template-initialized`) and refuses on a dirty tree without
`--force`.

### 3. Fill in the hardware context — the step that matters

Open `AGENTS.md` and complete the **Project context** section:

```
Target board / module:  Verdin iMX8MP Quad 4GB WB IT
Silicon revision:       ...
Memory:                 ...
Console:                /dev/serial/by-id/usb-FTDI_...
Recovery path:          USB recovery mode via the X1 connector, boot switch SW1
```

Most agent failures in embedded work are missing-context failures, not reasoning
failures. An agent that does not know the part number, the memory map and the recovery
path will produce confident, wrong answers — and may propose something irreversible.

### 4. Commit

```bash
git add -A
git commit -m "chore: initialize from embedded-agentic"
git push
```

---

## B. Add to an existing project

```bash
git clone https://github.com/toradex/embedded-agentic ~/tools/embedded-agentic
~/tools/embedded-agentic/install.sh ~/work/my-bsp --track linux
```

| Mode | Behaviour |
|------|-----------|
| `--mode link` (default) | symlinks into the template clone — improvements propagate to every project |
| `--mode copy` | self-contained copy — for handing a project to someone without the template |
| `--user` | also installs shared skills/agents into `~/.claude` for use across all projects |

Then fill in the project-specific section of the generated `AGENTS.md`. Field-by-field
templates are in `templates/mcu-project/` and `templates/linux-project/`.

---

## Wiring the hooks

```bash
ln -sf ../../hooks/pre-commit .git/hooks/pre-commit        # from a scaffolded project
ln -sf ../../.agents/hooks/pre-commit .git/hooks/pre-commit # from an install.sh install
```

Claude Code users: merge `hooks/settings.claude.json` into `.claude/settings.json` for
tool-call interception. Other harnesses get the same protection at the commit boundary
and in CI — see [`multi-harness.md`](multi-harness.md).

## Validating

```bash
./scripts/validate.sh
```

Checks skill and agent frontmatter, that names match filenames, that adapters are not
stale, that there are no dangling symlinks, and that hooks are executable and parse.

## Using it

Open your agent in the project. It should:

1. Identify the track and load the matching skill before acting
2. Ask for hardware context missing from `AGENTS.md`
3. State which testing layer produced each result — host, simulator, or hardware
4. Refuse irreversible hardware commands without your explicit confirmation

If it does not, the instruction file is not being read. Check that the adapter for your
harness exists (`./scripts/sync-agent-configs.sh`) and that you are running the agent
from the repository root.

## Staying current

```bash
./scripts/update-from-upstream.sh --dry-run
./scripts/update-from-upstream.sh
```

Pulls `shared/`, the track directories, `hooks/`, `scripts/` and `docs/` from upstream.
`AGENTS.md` is never overwritten — your hardware context stays. Upstream changes to the
rule sections are reported so you can merge them deliberately.

## Extending

```bash
mkdir -p mcu/skills/my-rtos
$EDITOR mcu/skills/my-rtos/SKILL.md     # frontmatter: name (= directory), description
$EDITOR mcu/AGENTS.md docs/skill-index.md   # add the routing entry
./scripts/sync-agent-configs.sh && ./scripts/validate.sh
```

Agents are markdown files in `<track>/agents/` with `name`, `description`, `tools` and
`model` frontmatter. Rules go in `shared/rules/` or a track's `rules/`, referenced from
the relevant `AGENTS.md`.

Contributions back to the template: see [`../CONTRIBUTING.md`](../CONTRIBUTING.md).

## What this does not do

It does not make an agent safe to point at production hardware. It removes a class of
failures — missing context, plausible-but-wrong embedded advice, unguarded destructive
commands. A human still decides what gets flashed.
