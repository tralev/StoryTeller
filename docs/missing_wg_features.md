# Remaining Worldgen and V2 Contract Gaps

Revalidated 2026-08-30. This is a diagnostic summary, not completion authority.
Use `roadmap.md` for delivery state and `worldgen-coverage.generated.md` for the
generated worldgen requirement ledger. The dated predecessor is retained as
`missing_wg_features.2026-08-05.md` and is intentionally stale.

## Current evidence

- Generated requirement counts are authoritative in
  `worldgen-coverage.generated.md`; do not copy counts into this diagnostic.
- P8.C05A–H and every active WG-INTEGRATION implementation row are complete;
  resolved prototype-defect rows remain obsolete.
- P8.C1 and P8.C2 are closed by their independent schema/prose gates and the
  generated 70-rule Python/Kotlin/Swift parity audit. File presence alone was
  not treated as closure evidence.
- P8.C05H has bounded real-model, Android, Swift, release-hardening, and
  accepted-package evidence. `scripts/generate_v2_fixtures.py` no longer
  overwrites authored v2 schemas (`properties` / `$defs`); `--check` compares
  the package corpus without writing `schemas/`.

## Closed contract gaps

### Deep v2 schemas (P8.C1)

Every file in `schemas/v2/` now has closed records and `$ref`s into
`defs.schema.json`. `scripts/audit_v2_schema_depth.py` passes. The generated
schema trace and independently transcribed contract-rule inventory pass, and the
recursive fixture catalog covers root schemas and otherwise unreachable shared
definitions. Those generated fixtures prove that the fixture generator follows
its inputs; they do not prove that the complete frozen prose contract is
represented. Generation now removes
uncatalogued stale files, and a test requires exact disk/catalog parity.
`generate_schemas()` may still emit stubs for unauthored files; it must not
clobber a schema that already has `properties` or `$defs`. Run:

```bash
.venv/bin/python scripts/audit_v2_schema_depth.py
```

P8.C1 is closed: clause ownership, prose classification, schema depth, recursive
fixture generation, native trusted bundles, and deterministic regeneration all
have executable gates.

### Three-validator parity (P8.C2)

Python, Kotlin, and Swift enforce all 70 inventoried validator rules, including
field-level schemas, replay, cross-reference rebuilding, local/macro
reconciliation, binary media, GM retrieval, resource admission, and ordered
diagnostics. The shared hostile/valid package corpus currently has 71 scenarios.

### Worldgen closure

- WG-HIST-004–013 have executable implementations and adversarial evidence.
  Rows 012–013 explicitly represent the phase-level megabeast and legendary-
  artifact lifecycle requirements omitted from the original eleven-row catalog.
- P8.C05G now has complete every-site generation, reconciliation, independently
  published chunks, bounded lazy reads, restart/corruption repair, storage
  budgets, narrative isolation, and accepted-package retention evidence.
- P8.C05H integration, hardening, zero-gap mapping, absorbed-document deletion,
  bounded real-model production, and native contract evidence are complete.

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

1. Keep P8.C1 schema/prose and P8.C2 parity audits as regression gates.
2. Continue with the next unchecked Phase 8 item in `roadmap.md`.
3. Keep physical-device, Wine, store, and release-scale evidence in Phase 9.
