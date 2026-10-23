# Distributed and IoT architecture for embedded devices

## Start with the link and failure model

Choose a network interface and protocol from range, power, bandwidth, topology, latency, payload, and deployment constraints. Treat connectivity as intermittent unless the system can demonstrate otherwise. Identify the link layer, addressing, routing, transport, application protocol, and security assumptions separately.

TCP/IP is widely interoperable but has code, memory, and operational costs. Constrained mesh or connectionless technologies can reduce some costs while introducing different delivery, routing, and management behavior. Compare measured resource use and ecosystem support on the target instead of selecting by name alone.

## Define communication boundaries

- Prefer a documented application protocol with explicit schema, units, versioning, timeouts, and error responses.
- Use request/response APIs where callers need immediate results; use message-oriented patterns when buffering, decoupling, or fan-out matters.
- Make retries bounded and safe. Operations with side effects need idempotency or a way to detect duplicate delivery.
- Set payload and queue limits. Specify what happens to delayed, duplicated, reordered, or malformed messages.
- Treat TLS configuration, credential provisioning, certificate rotation, and peer identity as part of the protocol design.

REST-style interfaces can be easy to inspect and integrate; brokered messaging can decouple producers and consumers. Neither removes the need to plan offline queues, backpressure, schema evolution, and operational monitoring.

## Avoid fragile dependencies

Map single points of failure across device, gateway, network, broker, cloud service, DNS, and identity services. For each, decide whether to fail closed, continue locally, buffer data, degrade functionality, or require operator action. Preserve essential local control when the external service is unavailable where system requirements permit.

## Review checklist

- [ ] Network and service failures have defined timeouts and bounded retry behavior.
- [ ] Offline operation and data buffering are bounded and documented.
- [ ] Messages identify schema version, units, device identity, and relevant timestamps.
- [ ] Authentication and encryption assumptions are explicit end to end.
- [ ] Critical functionality does not depend on an unexamined single remote service.
- [ ] Link and protocol choices have been measured on the target under expected coverage and power conditions.

Sources: *Embedded Systems Architecture*, 2nd ed., ch 9 (network interfaces, IP/TCP, sockets, TLS, application protocols and failure points).
