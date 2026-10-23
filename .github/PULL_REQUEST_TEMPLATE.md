## What

<!-- One or two sentences. What does this change for someone starting a project from this template? -->

## Type

- [ ] New skill (new ecosystem or tool)
- [ ] Skill improvement (new failure mode, corrected command, better routing)
- [ ] New or improved agent
- [ ] Rule change
- [ ] Harness support / tooling
- [ ] Docs

## Verification

- [ ] `./scripts/sync-agent-configs.sh` run; no hand-edited generated files
- [ ] `./scripts/validate.sh` passes
- [ ] `./scripts/init-project.sh` still produces a valid project
- [ ] Commands added to a skill were actually executed, not recalled

<!-- If this adds ecosystem knowledge, say where it came from: a real debugging session,
     vendor documentation (which version), or upstream source. -->

## Safety

- [ ] This does not weaken `.ai/rules/shared/10-hardware-safety.md` or the destructive-command guard
- [ ] If it does, explain why and tag a second reviewer
