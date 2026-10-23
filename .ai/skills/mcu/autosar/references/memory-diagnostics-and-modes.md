# Memory, Diagnostics, Modes, and Time

## Contents
- [Non-volatile memory](#non-volatile-memory)
- [Mode management](#mode-management)
- [Diagnostics and failure reporting](#diagnostics-and-failure-reporting)
- [Synchronized time](#synchronized-time)

## Non-volatile memory

NvM coordinates configured non-volatile storage objects through memory services and lower-level drivers. Identify block ownership, defaults, data integrity, write frequency, startup restore behavior, and failure reporting. Consider endurance, power-loss consistency, and compatibility when data layouts change.

## Mode management

BswM evaluates configured mode requests and rules to trigger ECU behavior such as communication state or shutdown sequencing. Map mode sources, arbitration, action lists, and transitions. Test conflicting requests, missing events, startup, sleep, wakeup, and shutdown paths.

## Diagnostics and failure reporting

DCM handles diagnostic communication services; DEM manages diagnostic events and associated status/storage behavior; DET reports development errors in applicable configurations. Trace a reported fault from detection through event reporting, storage, diagnostic response, and recovery. Separate development-only diagnostics from production behavior and ensure no sensitive data is exposed.

## Synchronized time

StbM provides a synchronized time base used by configured modules. CAN time synchronization may distribute time over the vehicle network. Check source, precision, validity, drift, timeout, and behavior during loss or resynchronization. Verify exact module responsibilities and APIs in the target release.

## Sources

- *AUTOSAR Fundamentals and Applications*, chapters 9–10.
