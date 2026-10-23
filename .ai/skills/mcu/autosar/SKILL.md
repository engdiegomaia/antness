---
name: autosar
description: Use when designing, configuring, reviewing, or debugging AUTOSAR Classic ECU software, including ARXML, system/ECU configuration, SWCs, ports/interfaces/events, RTE generation, MCAL/ECU Abstraction/Services, AUTOSAR OS tasks and interrupts, COM/PduR/CAN, Crypto Stack, NvM, BswM, DCM, DEM, DET, or StbM.
track: mcu
---

# AUTOSAR Classic Engineering

Use this skill to navigate AUTOSAR's model-driven ECU workflow. Keep application behavior, communication contracts, generated RTE, configured BSW, and hardware-specific MCAL responsibilities distinct. Confirm the AUTOSAR release, vendor toolchain, ECU variant, and project configuration before relying on module names or generated interfaces.

## Workflow

1. **Identify the platform and release.** Confirm Classic vs Adaptive, AUTOSAR release, ECU role, tool versions, supplier configuration, and applicable project standards.
2. **Trace the architecture.** Map system functions to SWCs, ports and interfaces, RTE communication, BSW services, ECU abstraction, MCAL, and hardware.
3. **Follow the model.** Inspect system and ECU descriptions, extract the relevant ARXML elements, and understand variant/configuration choices before editing. Keep models consistent across system, ECU, and generated outputs.
4. **Define component contracts.** Specify data types, sender-receiver or client-server behavior, events, timing, mode dependencies, and error behavior before RTE generation.
5. **Configure and generate.** Configure OS, COM stack, memory, diagnostics, security, and hardware modules through the project toolchain. Treat generated files as outputs; do not hand-edit generated code unless the project explicitly supports that workflow.
6. **Integrate and validate.** Check configuration consistency, generated interfaces, task/event activation, communication routing, startup/shutdown, diagnostics, and failure paths on the target or approved simulation environment.
7. **Maintain traceability.** Version ARXML, configuration, generated artifacts, tool versions, calibration, and ECU variants. Record deviations and link requirements to tests.

## Layer guide

| Layer | Responsibility | Review focus |
|---|---|---|
| Application SWCs | Product functions and component contracts | Port/interface semantics, runnables, data and timing |
| RTE | Generated communication and execution glue | Correct mapping, generated API consistency, task/event integration |
| Services | OS, communication, diagnostics, memory, security, and other common services | Configuration, lifecycle, error propagation |
| ECU Abstraction | Hides ECU-specific device details from upper layers | Device mapping and variant consistency |
| MCAL | Microcontroller-specific drivers and low-level access | Hardware configuration, timing, interrupts, safety constraints |
| Complex Drivers | Special functionality outside standard abstraction patterns | Ownership, interface boundary, and maintainability |

## Reference map

- [Architecture and methodology](references/architecture-and-methodology.md) — layers, VFB, system/ECU configuration, ARXML, and code generation.
- [SWCs, RTE, and communication contracts](references/swcs-rte-and-interfaces.md) — component types, ports, interfaces, events, and connectors.
- [AUTOSAR OS and scheduling](references/autosar-os-and-scheduling.md) — tasks, events, resources, interrupts, hooks, and timing.
- [Communication stack](references/communication-stack.md) — COM, PduR, CAN modules, PDUs, and network management.
- [Security, Crypto, and secure communication](references/security-and-crypto.md) — security concepts, Crypto Stack, secure diagnostics, and boot.
- [Memory, diagnostics, and modes](references/memory-diagnostics-and-modes.md) — NvM, BswM, DCM, DEM, DET, and time synchronization.

## Review checklist

- [ ] AUTOSAR platform, release, ECU variant, and supplier tooling are explicit.
- [ ] System and ECU models agree on SWCs, ports, data types, mappings, and variants.
- [ ] Generated RTE and BSW artifacts match the current configuration baseline.
- [ ] Task/event activation, priorities, resources, interrupts, and timing are reviewed together.
- [ ] Communication routing, update rates, timeouts, and error behavior are tested.
- [ ] NvM, mode transitions, diagnostics, and shutdown/restart paths are covered.
- [ ] Security and safety requirements are treated separately and traced to verification.

## Sources

- *AUTOSAR Fundamentals and Applications*, chapters 1–10.

AUTOSAR specifications and tool behavior evolve across releases and suppliers. Verify schema, module behavior, configuration constraints, and generated API names against the project's actual AUTOSAR release and vendor documentation.
