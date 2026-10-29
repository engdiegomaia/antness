# Antness Implementation Plan

## Goal

Evolve this repository into Antness, a local-first, hardware-aware CLI framework for MCU
and Embedded Linux development and validation. Antness should orchestrate existing project
toolchains, preserve hardware safeguards, and produce reviewable results with validation
provenance and evidence.

## Delivery phases

1. **Inventory and design:** map existing tools, workflows, configuration, and hardware
   safeguards; define the project configuration, result format, exit codes, and adapter
   contracts.
2. **CLI foundation:** provide project inspection, diagnosis, initialization, target and
   documentation management, stable JSON output, and clear configuration errors.
3. **Build and test:** wrap existing MCU and Linux commands, support ordered named
   workflows, and capture command, tool, timing, result, and evidence metadata.
4. **Hardware operations:** resolve targets, require policy-compliant confirmation for
   device-changing operations, serialize access to targets and probes, and collect logs.
5. **CI and adoption:** document installation, MCU and Linux quick starts, configuration,
   commands, safety, adapters, CI, troubleshooting, and migration. Retain existing tools
   until migration criteria are met.
6. **Advanced hardware context:** evaluate documentation indexing, schematic/netlist
   parsing, SVD-aware checks, and lab instrument adapters after the local project model
   stabilizes.

## Acceptance criteria

- `antness --help` and subcommand help describe supported commands and options.
- New, existing, and partially configured projects can be inspected and diagnosed without
  unexpected changes.
- Existing MCU and Linux tools remain available and are invoked through explicit adapters.
- Results distinguish host, simulator, target build, and physical hardware validation.
- Hardware-changing operations identify the target and require applicable authorization.
- Reports are available in text and JSON, include evidence references, and avoid leaking
  secrets.
- Reproducible setup, build, and test examples and migration guidance are documented.

## Current implementation status

The initial `antness.py` entry point supports project inspection, basic diagnosis,
configuration preview/creation, MCU build delegation, and explicitly configured build/test
commands. Workflow orchestration, full Linux adapters, target management, hardware command
groups, evidence reports, and the complete documentation set remain planned work.
