# Python sensor service and web interface

A small sensor-to-web service is a useful pattern when a supported kernel subsystem already exposes the hardware. Keep acquisition, state, and presentation separate:

1. **Acquire:** discover the device through its documented kernel interface (for example IIO), read values at a deliberate rate, and treat unavailable or invalid readings as explicit states.
2. **Normalize:** convert raw counts using the interface's scale/offset metadata where supplied; include units and sample time in the application model.
3. **Publish:** expose a narrow local or network API and a web view. Do not let request handlers perform unbounded device reads or block the event loop.
4. **Operate:** run under a service supervisor, log errors with rate limits, and define what the UI displays when data is stale or the sensor disappears.

Use the kernel's subsystem interface rather than hard-coding bus transactions in application code when an appropriate driver exists. Validate permissions and device-node ownership through the image configuration. Separate sensor sampling cadence from browser refresh cadence, and avoid implying precision beyond the sensor and driver specifications.

A prototype using Python, a light sensor, a time-series database and a web framework can illustrate the architecture, but its exact package names, IIO paths, database setup, and framework API are version- and board-dependent. Verify the target's IIO ABI and current Python packages before implementation.

## Checks

- [ ] Raw and converted values, units, timestamps and validity are explicit.
- [ ] Missing hardware and read failures do not crash the service or present stale data as live.
- [ ] Sampling and web refresh are decoupled and bounded.
- [ ] Network endpoints have access controls appropriate to their exposure.
- [ ] Device permissions are provisioned by the product image.

Sources: *Embedded Linux Essentials Handbook*, ch 9 (Python sensor web application, IIO and data presentation).
