# Getting Started

Two ways in: start a new project **from** the template, or add the environment **to** an
existing project.

---

## A. New project from the template

### 1. Create the repository

On GitHub: **Use this template → Create a new repository**.

Or from the CLI:
```bash
gh repo create my-project --template micron-iot/embedded-agentic --private --clone
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
git clone https://github.com/micron-iot/embedded-agentic ~/tools/embedded-agentic
~/tools/embedded-agentic/install.sh ~/work/my-bsp --track linux
```

| Mode | Behaviour |
|------|-----------|
| `--mode link` (default) | symlinks into the template clone — improvements propagate to every project |
| `--mode copy` | self-contained copy — for handing a project to someone without the template |
| `--user` | also installs shared and selected track harness sources into `~/.ai` for use across all projects |

Then fill in the project-specific section of the generated `AGENTS.md`. Field-by-field
templates are in `templates/mcu-project/` and `templates/linux-project/`.

---

## Wiring the hooks

```bash
```

Optional Claude Code hook settings are in `.ai/adapters/claude-hooks.json`; copy them into
your local harness configuration if you want tool-call interception. Other harnesses get the same protection at the commit boundary
and in CI — see [`multi-harness.md`](multi-harness.md). Claude Code 2.1.277+ reads the
canonical `AGENTS.md` directly when no `CLAUDE.md` is present in the repository path.

## Validating

```bash
./scripts/validate.sh
```

Checks skill and agent frontmatter, that names match filenames, that adapters are not
stale, that there are no dangling symlinks, and that hooks are executable and parse.

## AI-assisted implementation

Use the local step gate to keep agent changes small and evidence-backed:

```bash
python3 scripts/implementation_gate.py start --task "<task>" \
  --step "<one small change>" --acceptance "<observable outcome>"
```

Follow the `ready → implemented → verified → reviewed` sequence and record each gate's
evidence. A failed check blocks the step. See [`ai-assisted-workflow.md`](ai-assisted-workflow.md)
for the full lifecycle, stop conditions, and offline evaluations.

## Using it

Open your agent in the project. It should:

1. Identify the track and load the matching skill before acting
2. Ask for hardware context missing from `AGENTS.md`
3. State which testing layer produced each result — host, simulator, or hardware
4. Refuse irreversible hardware commands without your explicit confirmation

If it does not, check that the harness reads `AGENTS.md` and follows its `.ai/` references and that you are running the agent from the
repository root. Configure harness-specific tool settings locally; do not commit vendor-specific config directories.

## Staying current

```bash
./scripts/update-from-upstream.sh --dry-run
./scripts/update-from-upstream.sh
```

Pulls `.ai/`, executable track tools, runtime libraries, scripts and docs from upstream.
`AGENTS.md` is never overwritten — your hardware context stays. Upstream changes to the
rule sections are reported so you can merge them deliberately.

## Extending

```bash
mkdir -p .ai/skills/mcu/my-rtos
$EDITOR .ai/skills/mcu/my-rtos/SKILL.md     # frontmatter: name (= directory), description
$EDITOR .ai/tracks/mcu/AGENTS.md docs/skill-index.md   # add the routing entry
./scripts/sync-agent-configs.sh && ./scripts/validate.sh
```

Agents are Markdown files in `.ai/agents/<track>/` with `name`, `description`, `tools` and
`model` frontmatter. Rules go in `.ai/rules/shared/` or `.ai/rules/<track>/`, referenced from
the relevant `AGENTS.md`.

Contributions back to the template: see [`../CONTRIBUTING.md`](../CONTRIBUTING.md).

## What this does not do

It does not make an agent safe to point at production hardware. It removes a class of
failures — missing context, plausible-but-wrong embedded advice, unguarded destructive
commands. A human still decides what gets flashed.
