# Qt applications that interact with hardware

Use Qt when the product needs a native graphical interface and the target image can support the chosen Qt modules, display backend, and licensing model. Cross-build against a Qt SDK generated for the target or otherwise matched to the target sysroot; host Qt libraries are not a substitute for target libraries.

## Keep the UI responsive

- Treat the GUI event loop as a serialization boundary for UI state. Hardware acquisition, slow disk work, and network requests must not block it.
- Use asynchronous APIs, worker objects/threads, or a message boundary for operations with uncertain latency. Return results to the UI thread through supported Qt mechanisms.
- Distinguish command submission from completion. Show pending, success, failure, and stale-data states rather than assuming a button click means hardware changed.
- Validate user input at the boundary and keep device state as the source of truth; UI labels and colors are derived presentation.
- Stop workers and release hardware resources during shutdown.

## Cross-build and deploy

Use a target Qt kit containing the compiler, debugger, headers, and libraries that match the image. Deploy the application with compatible Qt runtime plugins and platform integration. Verify graphics/input backend, fonts, plugin discovery, and runtime libraries on the actual image. Qt Creator project format and Qt module APIs vary by release; examples based on older Qt 5/qmake workflows should be adapted to the product's supported Qt version and build system.

The book's scientific-instrument and medical-device examples demonstrate hardware interaction and UI event handling only. A GUI prototype is not evidence of functional safety, clinical validity, risk controls, or regulatory compliance.

## Checks

- [ ] UI remains responsive during sensor, storage and network delays.
- [ ] Device failures and disconnects are represented clearly.
- [ ] The UI cannot claim an operation succeeded before receiving confirmation.
- [ ] Target Qt libraries, plugins and ABI match the root filesystem.
- [ ] Safety-critical behavior has a separate requirements and verification process.

Sources: *Embedded Linux Essentials Handbook*, ch 10 (Qt instrument application, asynchronous hardware interaction) and ch 11 (Qt UI and synchronous command example).
