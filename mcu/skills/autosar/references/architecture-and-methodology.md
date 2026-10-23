# AUTOSAR Architecture and Methodology

## Contents
- [Understand the layered architecture](#understand-the-layered-architecture)
- [Follow the V-model and data flow](#follow-the-v-model-and-data-flow)
- [Work with ARXML models](#work-with-arxml-models)
- [Control code generation](#control-code-generation)

## Understand the layered architecture

AUTOSAR Classic separates application software from ECU-specific implementation through the Runtime Environment (RTE) and Basic Software (BSW). The application layer contains SWCs; the RTE connects their modeled ports to other components and BSW services. BSW includes service modules, ECU Abstraction, and MCAL. Complex Drivers provide controlled exceptions where standard interfaces do not fit.

The Virtual Functional Bus (VFB) is a system-level view of communication among components before mapping to a particular ECU. It helps separate functional design from deployment, but the final mapping still has resource, timing, and hardware constraints.

## Follow the V-model and data flow

System configuration describes functions and allocation across ECUs. ECU configuration refines the selected ECU's SWCs, mappings, BSW modules, and hardware-specific parameters. RTE and BSW outputs are generated from these models and configuration. Trace a requirement through system design, ECU mapping, configuration, generated code, and test evidence.

## Work with ARXML models

ARXML is a structured exchange format for AUTOSAR models and configuration. Use the authoring and configuration tools to preserve schema, references, variation points, and supplier extensions. Before editing, identify the owning model and the tools that consume it. Validate imports and schema consistency with the project's supported release rather than making textual edits based on appearance alone.

## Control code generation

Generated code is derived from model and configuration inputs. Track tool versions, templates, configuration, and generator options so output can be reproduced. Compare generated interfaces after configuration changes and investigate unexpected diffs. Keep hand-written code in supported integration points rather than modifying generator output directly.

## Sources

- *AUTOSAR Fundamentals and Applications*, chapters 1–3.
