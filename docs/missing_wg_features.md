# Remaining Worldgen and V2 Contract Gaps

Revalidated 2026-08-23. This is a diagnostic summary, not completion authority.
Use `roadmap.md` for delivery state and `worldgen-coverage.generated.md` for the
generated worldgen requirement ledger. The dated predecessor is retained as
`missing_wg_features.2026-08-05.md` and is intentionally stale.

## Current evidence

- Generated requirement counts are authoritative in
  `worldgen-coverage.generated.md`; do not copy counts into this diagnostic.
- P8.C05A–G and every active WG-INTEGRATION implementation row are complete.
  P8.C05H remains open only while its real-model/default-profile/native exit
  evidence is being audited; resolved prototype-defect rows remain obsolete.
- P8.C1 and P8.C2 remain open. File presence, generated fixtures, or coarse
  validator stages do not satisfy their exit criteria.
- P8.C05H integration through P4 is on `main` (through `dffda3f`). Remaining
  C05H exit is real-model/default-profile/native evidence, not more integration
  code. `scripts/generate_v2_fixtures.py` no longer overwrites authored v2
  schemas (`properties` / `$defs`); `--check` compares the package corpus
  without writing `schemas/`.

## Confirmed open gaps

### Deep v2 schemas (P8.C1)

Every file in `schemas/v2/` now has closed records and `$ref`s into
`defs.schema.json`. `scripts/audit_v2_schema_depth.py` passes. Remaining
P8.C1 work is the prose-to-schema trace matrix and three-validator field
parity (P8.C2). The fixture catalog currently contains 213 documents
generated from those schemas. They prove that the fixture generator follows its inputs; they do not
prove that the frozen product contract is represented. Generation now removes
uncatalogued stale files, and a test requires exact disk/catalog parity.
`generate_schemas()` may still emit stubs for unauthored files; it must not
clobber a schema that already has `properties` or `$defs`. Run:

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

- WG-HIST-004–013 have executable implementations and adversarial evidence.
  Rows 012–013 explicitly represent the phase-level megabeast and legendary-
  artifact lifecycle requirements omitted from the original eleven-row catalog.
- P8.C05G now has complete every-site generation, reconciliation, independently
  published chunks, bounded lazy reads, restart/corruption repair, storage
  budgets, narrative isolation, and accepted-package retention evidence.
- P8.C05H integration, hardening, zero-gap mapping, and absorbed-document
  deletion are implemented. Its broader operational/native exit evidence is
  tracked separately from the completed WG-INTEGRATION rows.

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
2. Finish the explicitly required P8.C05H operational/native evidence without
   misclassifying P8.C1/P8.C2 or Phase 9 device/release work as implementation.
3. Run full field-level native parity only after schema closure.
