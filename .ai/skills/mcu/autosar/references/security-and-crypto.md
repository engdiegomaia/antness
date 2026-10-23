# AUTOSAR Security and Crypto Stack

## Contents
- [Separate safety and security](#separate-safety-and-security)
- [Map Crypto Stack responsibilities](#map-crypto-stack-responsibilities)
- [Secure communications and diagnostics](#secure-communications-and-diagnostics)
- [Secure boot integration](#secure-boot-integration)

## Separate safety and security

Safety addresses hazards from malfunction; security addresses intentional misuse and attack. They can interact, but evidence and processes are distinct. Threat-model assets, actors, interfaces, trust boundaries, and failure impact alongside safety analysis.

## Map Crypto Stack responsibilities

AUTOSAR Crypto Stack modules abstract cryptographic services and route requests to software or hardware implementations. The book describes Crypto Service Manager, Crypto Interface, and Crypto Driver roles. Verify exact module names, job model, key handling, and configuration against the project's AUTOSAR release and vendor implementation.

Use approved algorithms and key sizes under the project's current security policy. Define key provisioning, access control, rotation, revocation, and failure handling. Do not place secrets in ordinary application configuration or logs.

## Secure communications and diagnostics

Secure communication requires freshness, authentication, integrity, and replay protection appropriate to the threat model; encryption alone does not provide all of these. Secure diagnostics should authenticate access and limit permitted operations by role and vehicle state. Test unauthorized, stale, malformed, and replayed requests.

## Secure boot integration

Secure boot verifies authenticity and integrity of executable stages before use. Trace the root of trust, bootloader and image verification, key storage, update signing, rollback policy, and recovery. AUTOSAR modules may participate in an ECU security design, but the complete boot chain and hardware must enforce it.

## Sources

- *AUTOSAR Fundamentals and Applications*, chapter 8.
