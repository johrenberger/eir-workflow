# EIR Domain 3 Implementation Postmortem

## Outcome

The experimental runtime completed an official-source 2025 FOMC workflow with complete claim coverage, independent verification, and an auditable `SUPPORTED` terminal result. The implementation stayed within the frozen EIR v1.0 top-level schema.

## What worked

- Claim-universe planning separated completeness from evidence interpretation.
- Offline synthetic tests enabled reliable control-path development before live retrieval.
- SQLite checkpoints and content hashes made restart, audit, and provenance practical.
- Explicit D1/D2/N1/L4/H1 boundaries prevented model-led completion claims.
- Route policy injection made changed-strategy recovery deterministic and testable.

## What required correction

- State additions need migration-safe defaults; old runs initially lacked newer optional fields.
- Phase guards exposed an ordering issue: the meeting universe must be checkpointed before retrieval is recorded as research work.
- System-temp assumptions are brittle in sandboxed environments; tests need a workspace-local base-temp option.
- A generic artifact-template system was not a fit for a Python runtime; the appropriate reusable outputs are a personal skill and repository-native template guide.

## Limits and follow-up

- Evidence-quality scoring is intentionally transparent but lightweight.
- The official route policy covers known FOMC statement, implementation, and minutes paths; other domains need their own deterministic policy.
- Live tests should remain opt-in and use a dedicated schedule/manual workflow in CI.
- Production deployment would need authentication handling, rate limits, external human-review identity, and stronger concurrent-run coordination.
