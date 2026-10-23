# AI-assisted implementation workflow

Use this workflow for bounded code and configuration changes. It is provider-neutral:
the same acceptance criteria, step gates, and safety rules apply regardless of which
agent or harness performs the work.

## Work in small steps

1. Inspect the repository, applicable `AGENTS.md` files, track rules, and relevant skill.
   Identify unknown hardware or toolchain facts before proposing a change.
2. Break the task into independently reviewable changes. Each step should have one
   observable outcome and acceptance criteria. Keep hardware operations and unrelated
   cleanup out of the step.
3. Start a step with `scripts/implementation_gate.py start`. The tool stores progress in
   `.embedded-agentic/implementation.json`, which is local and git-ignored.
4. Implement only the active step. Record what changed to move from `ready` to
   `implemented`.
5. Run the narrowest checks that establish the acceptance criteria, then relevant wider
   checks. Record a passing command to move to `verified`. A failed check records the
   failure and blocks progress; fix it and rerun before advancing.
6. Inspect the diff against the acceptance criteria and review triggers. Record review
   evidence to move to `reviewed`. Only then start the next baby step.
7. Report completed steps, commands and outcomes, validation environment (host,
   simulator, or hardware), remaining limitations, and the final diff summary.

Example:

```bash
python3 scripts/implementation_gate.py start \
  --task "Add sensor timeout handling" \
  --step "Return a timeout error from the sensor read helper" \
  --acceptance "The helper returns a timeout error when data is not ready"

python3 scripts/implementation_gate.py advance --to implemented \
  --evidence "Updated the helper and added the timeout branch"
python3 scripts/implementation_gate.py advance --to verified \
  --check "python3 -m unittest discover -s tests -v" --result passed
python3 scripts/implementation_gate.py advance --to reviewed \
  --evidence "Reviewed the diff against the acceptance criteria; no findings"
python3 scripts/implementation_gate.py start \
  --task "Add sensor timeout handling" \
  --step "Expose timeout count in diagnostics" \
  --acceptance "Diagnostics report timeout count without blocking the ISR"
```

Use `python3 scripts/implementation_gate.py status` to inspect the active step. The gate
records evidence but does not execute validation or review commands; the agent/operator
must run them and report accurately. Never claim a check passed based only on its name.

## Stop conditions and guardrails

Stop at the current step and report the blocker when requirements conflict, acceptance
criteria cannot be verified, a check fails, the change expands beyond its stated scope,
or required repository/hardware facts are missing. Resolve the issue or get the needed
human input before continuing. Do not silently mark a blocked step complete.

Existing controls remain mandatory:

- Irreversible writes to flash, eMMC, fuses, bootloader environment, or secure boot keys
  require explicit confirmation for that exact operation and target.
- Do not infer board facts, register values, pins, or recovery procedures. Cite the
  repository or vendor source, or ask for the missing information.
- Preserve pinned toolchains and reproducible build commands. Do not change versions as
  an incidental part of another task.
- Select checks according to risk and report where each result was obtained. Host or
  simulator evidence must not be presented as hardware validation.
- Keep scope narrow. If the plan needs to change, record the new acceptance criteria
  before implementing the expanded step.

## Offline evaluations

Run `python3 -m unittest discover -s evals -v` to exercise the workflow contract without
model calls, credentials, or hardware. The cases cover valid stage progression, evidence
requirements, skipped-stage rejection, failed-check blocking, and preservation of prior
baby-step history. Existing CI safety scenarios continue to verify hardware command
guardrails. The suite also exercises the destructive-command guard: irreversible flash,
fuse, and block-device writes must be blocked, while build and read-only commands remain
allowed. Runtime tests cover structured validation provenance. When adding a workflow
rule, add a passing case, a counterexample that must be rejected, and an unrelated case
where the rule must not interfere.

## Design references

- OpenAI, [Harness engineering](https://openai.com/index/harness-engineering/): keep
  repository knowledge legible and pair agent work with enforceable feedback loops.
- OpenAI, [Evaluate agent workflows](https://developers.openai.com/api/docs/guides/agent-evals):
  evaluate workflow decisions and rerun regressions when instructions or routing change.
- GitHub, [Best practices for using Copilot to work on tasks](https://docs.github.com/en/copilot/tutorials/cloud-agent/get-the-best-results):
  scope tasks clearly and define acceptance criteria before implementation.
