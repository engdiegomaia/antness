---
name: requirements-traceability
description: Linking requirements to design, code, and tests for regulated or safety-relevant embedded products (IEC 61508, ISO 26262, IEC 62304, IEC 62443, EU CRA).
track: both
---

# Requirements Traceability

## When this applies

Any product subject to functional safety, medical, automotive, industrial security, or
the EU Cyber Resilience Act. If the product is in scope, traceability is a deliverable,
not documentation overhead — and an untraceable change is a non-conformance regardless
of whether the code is correct.

Ask early: **is this product in a regulated scope?** The answer changes the workflow.

## The chain

```
Requirement -> Architecture element -> Implementation -> Verification -> Evidence
   REQ-042        ARCH-SENSOR           src/sensor.c      TC-042        test log + review record
```

Every link is bidirectional and every link is named in an artifact, not in someone's head.

## Practical mechanics

```c
/*
 * Implements: REQ-042 (sensor sample rate 100 Hz +/- 1%)
 * Verified by: TC-042
 */
```

```python
# test_sensor.py
def test_sample_rate_within_tolerance():
    """Verifies: REQ-042"""
```

Commit message:
```
feat(sensor): add 100 Hz sampling

Implements: REQ-042
Verified-by: TC-042
Validated-on: verdin-imx8mp rev 1.1B, image sha256:...
```

A grep over the repository must be able to answer "where is REQ-042 implemented and
tested". If it cannot, the traceability is decorative.

## Change impact

For any change to a traced item, state:
- Which requirements are affected
- Which tests must be re-run (not "all tests" — the specific ones, plus a regression set)
- Whether the change affects a safety function or a security control
- Whether re-certification or a notified-body notification is triggered

## Tool-qualification note

In regulated development, a tool that can introduce an error into the product without
detection must be qualified. **An AI agent generating production code falls into this
discussion.** The defensible position is that the agent's output is reviewed and verified
by qualified humans and by the verification chain — which means the review record must
exist, be attributable, and be retained.

Practical consequence: agent-generated code in a regulated product must show
- who reviewed it,
- against which requirement,
- and which test evidence covers it.

Record that in the commit and the review artifact. Do not obscure that a change was
agent-assisted; the traceability record is more useful when it is accurate.

## Standards quick map

| Standard | Domain | Key traceability demand |
|----------|--------|-------------------------|
| IEC 61508 | Functional safety (generic) | SIL-dependent V-model, systematic capability |
| ISO 26262 | Automotive | ASIL decomposition, ToolQualification (ISO 26262-8) |
| IEC 62304 | Medical software | Software safety class, SOUP inventory |
| IEC 62443-4-1/4-2 | Industrial security | Secure development lifecycle, threat model per requirement |
| EU CRA | Products with digital elements | SBOM, vulnerability handling, support period |
| DO-178C | Airborne | Objectives per level, structural coverage (MC/DC at Level A) |

Note SOUP/SBOM explicitly: every third-party component in the image is an inventory
item with a version, a license, and a vulnerability-monitoring obligation.
