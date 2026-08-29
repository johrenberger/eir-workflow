# EIR Domain 3 runtime

An offline-first, SQLite-backed implementation of the supplied EIR v1.0 Domain 3 research test. It does not contain or hard-code the 2025 FOMC answer.

```bash
python -m pip install -e ".[dev]"
pytest
eir-runtime validate fixtures/domain3.yaml
eir-runtime status fixtures/domain3.yaml --db state/fomc-live.sqlite --run-id fomc-2025
```

Default tests use synthetic schedule and statement fixtures only. Live retrieval is deliberately opt-in.

## Architecture

```mermaid
flowchart TD
  EIR["Frozen EIR v1.0\n13 top-level sections"] --> V["V001–V020 validation"]
  V -->|valid| C["Research controller\nSQLite-backed run state"]
  V -->|invalid| F["FAILED"]

  C --> D1["D1: calendar / route planning\nclaim universe / checks"]
  D1 --> R["Official retrieval adapter\ncontent-addressed artifacts"]
  R --> D2["D2: bounded grounded extraction"]
  D2 --> G["Claim/evidence graph\nquality + progress metrics"]
  G --> I["Independent verifier"]

  G -->|contradiction| N1["N1: bounded ambiguity\ninterpretation only"]
  N1 --> L4["L4: distinct authoritative\nadjudication"]
  L4 -->|unresolved / exhausted| H1["H1: durable human handoff"]
  H1 -->|human resolution| C

  R -->|failure| CTRL["S12 control router\nretry → L3 route policy → L4/H1"]
  CTRL --> R
  I --> T{"Deterministic completion"}
  T --> S["SUPPORTED"]
  T --> IE["INSUFFICIENT_EVIDENCE"]
  T --> F
  C --> O["Status + JSON audit bundle"]
```

For an official-only run:

```bash
eir-runtime live fixtures/domain3.yaml --db state/fomc-live.sqlite --run-id fomc-2025
```

The runtime stores immutable content-addressed source artifacts, the source registry, action history, failure fingerprints, uncertainty records, and claim/evidence links in the SQLite database. Reusing a nonterminal run ID reconciles recorded inflight work; it never infers completion from interruption.

The canonical EIR top-level schema remains frozen at 13 sections. Claims, sources, citations, and hypotheses are runtime records held in the EIR `state`/`evidence` sections, not EIR primitives.
