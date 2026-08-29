# Evidence-First Research Project Template

Use this repository as the implementation template for a bounded research question that needs auditable evidence rather than a narrative-only result.

## Configure

1. Copy `fixtures/domain3.yaml` to a domain-specific EIR fixture.
2. Preserve the 13 frozen EIR v1.0 top-level sections.
3. Define the authoritative system, permitted source classes, limits, required coverage, and terminal contract.
4. Replace the FOMC calendar planner and route policy with deterministic domain adapters.
5. Add synthetic fixtures before enabling a live adapter.

## Required design decisions

- What establishes the complete universe of required claims?
- Which source class is sufficiently authoritative for each material claim?
- What makes two sources independent rather than derivative?
- Which failures are retryable, and what constitutes a material L3 strategy change?
- When must unresolved uncertainty stop at H1 rather than continue automatically?

## Acceptance checklist

- Invalid EIR input fails before side effects.
- Every required claim is durable and evidence-linked.
- Extraction is schema-bounded and span-grounded.
- Progress is based on sufficiency, not activity volume.
- Retries, L3 changes, L4 adjudications, and H1 handoffs are inspectable.
- Terminal output is independently verified and includes claim-level provenance.
- Default CI is synthetic/offline; live integration is opt-in.
