# StoryTeller Documentation Index

## Authority

This directory is the sole documentation authority for StoryTeller's product
target, contracts, decisions, implementation plan, and verification criteria.
Source code, generated schemas, fixtures, and test evidence prove implementation;
unchecked roadmap items are requirements, not claims of completed behavior.

When documents disagree, use this order:

1. Accepted decisions in `decisions.md` and the normative target in `package-v2.md`
2. `api.md` for public behavioral contracts
3. `arch.md` for implementation and data architecture
4. `design.md` for logical flow and user behavior
5. `goal.md` for product scope and non-goals
6. `roadmap.md` for delivery order, not final contract definition
7. `legacy.md` only as a comparison/history record

The prose v2 contract is frozen. Schemas, fixtures, and three validators become
executable authorities only to the extent that they express it exactly; known
conformance debt is tracked as P8.C1–P8.C2. If implementation evidence exposes
an impossible detail, change the
decision record and every affected contract together before changing code.

## Recommended reading order

### Product and contributor overview

1. `readme.md`
2. `goal.md`
3. `design.md`
4. `worldgen-coverage.generated.md`
5. `worldgen-references.md`
6. `ux.md`
7. `arch.md`
8. `api.md`

### Implementation planning

1. `decisions.md`
2. `configuration.md`
3. `prompts.md`
4. `diagnostics.md`
5. `roadmap.md`
6. `test.md`
7. `threat-model.md`
8. `compliance.md`
9. `accessibility.md`
10. `release.md`

### Format implementation

1. `arch.md`
2. `api.md`
3. `package-v2.md`
4. `glossary.md`
5. `test.md`

## Document catalog

| Document | Audience | Purpose | Status |
|---|---|---|---|
| `readme.md` | Users and contributors | Target product introduction and workflows | Target |
| `goal.md` | Everyone | Product boundaries, principles, success criteria | Target |
| `design.md` | Product and engineering | Logical generation, Player, GM, save, and GUI flows | Target |
| `worldgen-references.md` | World and simulation engineering | Comparative generators, research uses, and license/provenance rules | Living reference |
| `worldgen-coverage.generated.md` | Worldgen engineering | Checked replacement ledger for the absorbed generation/rewrite specifications | Current generated evidence |
| `missing_wg_features.md` | Worldgen engineering | Current implementation-gap audit against the checked ledger | Current audit |
| `missing_wg_features.2026-08-05.md` | Maintainers | Superseded pre-deletion worldgen gap audit | Archive only |
| `recommendations.md` | Maintainers | Superseded Phase 5.6 hardening plan retained for history | Archive only |
| `arch.md` | Engineering | Components, ports, validators, backends, models, and data architecture | Target |
| `api.md` | Engineering/integrators | Python, CLI, event, package, Player, save, and GM contracts | Target |
| `configuration.md` | Users and engineering | Typed settings, precedence, model registry, policies, and CLI mapping | Target; generated field reference remains planned |
| `prompts.md` | Prompt and pipeline engineering | Prompt identity, versioning, resolution, rendering, and provenance | Target |
| `ux.md` | Product, desktop, and mobile | Launcher, library, import, reader, save, ending, and GM interactions | Target |
| `diagnostics.md` | Engineering, support, and QA | Stable diagnostic codes, retry behavior, and recovery actions | Target catalog |
| `test.md` | Engineering/QA | Verification strategy and release gates | Target |
| `compliance.md` | Release/legal review | Privacy, model licenses, mature content, stores | Recheck each release |
| `accessibility.md` | Product/mobile/QA | Inclusive reader, GM, media, and launcher requirements | Target |
| `threat-model.md` | Engineering/security | Assets, trust boundaries, threats, mitigations, security gates | Target |
| `package-v2.md` | Format implementers | Normative frozen package specification; executable-schema closure is P8.C1–P8.C2 | Binding target |
| `decisions.md` | Contributors | Accepted decisions and consequences | Living target record |
| `glossary.md` | Everyone | Canonical terminology | Living target record |
| `release.md` | Maintainers | Reproducible release process and evidence | Target |
| `roadmap.md` | Contributors | Remaining implementation, hardening, and release evidence | Current plan |
| `legacy.md` | Maintainers | Historical disposition ledger; never normative | Archive only |
| `pipeline.generated.md` | Engineering | Generated snapshot of the sole procedural-first production plan; not target authority | Current generated evidence |
| `cli-help.generated.txt` | Users/engineering | Generated current CLI help | Current generated evidence |
| `world-controls.generated.md` | Users/engineering | Generated WorldSpec defaults, CLI mappings, fixed invariants, and resume policy | Current generated evidence |

## Maintenance rules

- Do not put current implementation percentages or volatile test counts in
  future-state documents.
- Mark roadmap checkboxes complete only with the evidence required by that phase.
- Use `decisions.md` before changing a product invariant.
- Update `api.md`, schemas, `package-v2.md`, fixtures, and all three validators in
  the same change when a frozen public contract changes.
- Generate pipeline/CLI tables from executable contracts where possible.
- Date and cite time-sensitive compliance claims.
- Never silently turn a target requirement into an implementation observation.

## Authority boundary

Files outside this directory may contain historical or implementation notes, but
they cannot redefine the product. Generated JSON Schemas become executable format
authorities only when they exactly implement `package-v2.md`; disagreement is a
release-blocking documentation/schema defect.
