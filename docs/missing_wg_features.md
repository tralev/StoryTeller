# Remaining Worldgen and V2 Contract Gaps

Revalidated 2026-08-15. This is a diagnostic summary, not completion authority.
Use `roadmap.md` for delivery state and `worldgen-coverage.generated.md` for the
generated worldgen requirement ledger. The dated predecessor is retained as
`missing_wg_features.2026-08-05.md` and is intentionally stale.

## Current evidence

- The generated ledger contains **96 requirements: 62 complete, 28 partial,
  0 missing, and 6 obsolete**.
- P8.C05A–D are complete. All 16 `WG-SOC-*` rows provide named evidence, so
  P8.C05E is complete. P8.C05F–H remain open.
- P8.C1 and P8.C2 remain open. File presence, generated fixtures, or coarse
  validator stages do not satisfy their exit criteria.
- The worktree contains a substantial uncommitted Phase 8 rewrite. Its modules
  and focused tests are useful evidence, but they are not a release milestone.

## Confirmed open gaps

### Deep v2 schemas (P8.C1)

Twenty of the 22 files in `schemas/v2/` are shallow top-level schemas. The whole
directory is approximately 5.8 KB, not 45 KB. Required fields such as
`terrain.chunk_shape` and `history.events` lack typed definitions, most roots do
not set `additionalProperties: false`, and nested records remain unspecified.
The other two schemas also fail full-depth closure because nested records remain
open-ended, so the executable gate currently reports 22 of 22 failures.

The fixture catalog currently contains 71 documents generated from those
schemas. They prove that the fixture generator follows its inputs; they do not
prove that the frozen product contract is represented. Generation now removes
uncatalogued stale files, and a test requires exact disk/catalog parity. Run:

```bash
.venv/bin/python scripts/audit_v2_schema_depth.py
```

P8.C1 cannot close until that command passes and the normative rule trace has no
untyped or unconstrained contract records.

### Three-validator parity (P8.C2)

Python, Kotlin, and Swift share coarse archive stages for ZIP safety, manifest
version, inventory/hash checks, dependency existence, layout, and mandatory
media. They do not yet enforce complete field-level domain schemas, replay,
cross-reference rebuilding, local/macro reconciliation, or the full hostile
catalog identically. P8.C2 depends on completed P8.C1 schemas.

### Worldgen closure

- P8.C05F has complete monthly and yearly proposal coverage, but still has
  partial proposal-conflict, event-envelope, replay, retention, and
  checkpoint/resume requirements.
- P8.C05G still needs complete every-site 3D generation and reconciliation proof.
- P8.C05H still needs integration hardening and the final zero-gap/deletion gate.

### Media contract

Frozen v2 publication requires complete image and MIDI coverage. Production
configuration and both acceptance paths now require `1.0` for both. Constructing
a lower Phase 5.6 threshold policy is rejected.

### External evidence

Real-model end-to-end generation, physical-device runs, Wine/native packaging,
privacy/store evidence, accessibility, and release performance remain Phase 9
gates.

## Corrected non-gap

There is no demonstrated `world/artifacts/` versus
`world/authoritative/artifacts/` packager mismatch. `SimulateWorldStage` passes
`world/authoritative` as the world root, and `package_project_v2()` correctly
reads its `artifacts/` child. The integrated packaging contract test passes.

## Recommended order

1. Keep P8.C1/P8.C2 visibly open and deepen schemas in dependency order.
2. Continue P8.C05F with immutable proposal collection and conflict resolution
   under `WG-HIST-004`; yearly proposal coverage is complete.
3. Complete P8.C05F proposal/replay/checkpoint guarantees, then P8.C05G/H.
4. Run shared native parity and Phase 9 evidence only after schema closure.
