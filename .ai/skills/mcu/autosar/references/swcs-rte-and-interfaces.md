# Software Components, RTE, and Interfaces

## Contents
- [Model an SWC](#model-an-swc)
- [Choose ports and interfaces](#choose-ports-and-interfaces)
- [Connect data and behavior](#connect-data-and-behavior)
- [Generate and validate the RTE](#generate-and-validate-the-rte)

## Model an SWC

An SWC encapsulates application behavior behind modeled interfaces. Its internal behavior is implemented by runnables and associated data, events, and access points. Component types and composition structure should reflect ownership and change boundaries rather than merely mirror source files.

Define data types, units, ranges, invalid values, and update semantics explicitly. Document initialization and behavior when inputs are stale, unavailable, or outside expected range.

## Choose ports and interfaces

Sender-receiver communication conveys data elements, often with implicit or explicit update timing. Client-server communication models a request and response operation. Select the contract that matches the interaction and specify queueing, timing, error, and concurrency behavior in the model.

Ports connect SWCs to other SWCs or services. Composition connectors express the system-level wiring. Check directions, interface types, data compatibility, and instance mapping before generation.

## Connect data and behavior

Events activate runnables according to modeled conditions such as data arrival, operation invocation, timing, or mode change. Verify that event sources and runnable timing align with task activation and execution requirements. A port connection alone does not prove that a runnable executes at the required rate.

## Generate and validate the RTE

RTE generation maps modeled interfaces onto ECU-specific communication and execution mechanisms. Inspect generated headers and APIs after configuration changes. Validate that runnable entry points, data access, client/server calls, and error return paths match the model and intended behavior.

## Sources

- *AUTOSAR Fundamentals and Applications*, chapters 4–5.
