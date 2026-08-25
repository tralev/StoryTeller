# StoryTeller Target Diagnostics Catalog

## Purpose

This document defines stable, user-actionable diagnostic codes shared by Forge,
the launcher, package validators, and Players. It is a target contract; code and
tests must generate their reference tables from the same typed catalog.

## Diagnostic envelope

```json
{
  "code": "ST-MODEL-002",
  "severity": "error",
  "category": "dependency",
  "message": "The selected model file does not match its registry checksum.",
  "operation": "models.verify",
  "run_id": "optional-run-id",
  "artifact_id": null,
  "node_id": null,
  "retryable": false,
  "action": "Download the registered model again.",
  "details_ref": "diagnostics/run-id/ST-MODEL-002.json"
}
```

User-facing messages are localizable and contain no secrets or stack traces.
Structured details remain local and may include causes, hashes, versions, and
bounded paths after redaction.

## Code format

`ST-<DOMAIN>-<NNN>` uses a stable uppercase domain and three-digit number. Once
released, a code's meaning is never reused. Wording may improve without changing
the code; category, retry semantics, or recovery meaning require a new code.

**Implementation status:** this grammar is a target contract, not yet adopted
anywhere in production code. No `ST-<DOMAIN>-<NNN>` code exists in `src/`
today. Current code uses at least two other ad-hoc, undocumented schemes that
predate this contract: `src/pipeline/errors.py`'s `StoryTellerError` hierarchy
(abbreviated-domain-plus-number codes like `CFG_001`, `DEP_001`, `PKG_001`,
labeled Phase 5.5F, superseded by the domain-specific diagnostics this file
now defines and not confirmed still reachable from the current pipeline), and
free-text hyphenated `ValueError` message prefixes used throughout `src/world`,
`src/narrative`, `src/worldgen`, and `src/validators` (for example
`BEAT-TICK`, `GRAPH-ENTITY-STATE`, `PACKAGE-*`, `WG-CIV-CAPACITY`). Migrating
either scheme to this contract is unscheduled future work, not part of any
current roadmap item; do not assume a code documented here is raisable by any
existing code path until it is.

Domains are `CONFIG`, `MODEL`, `RESOURCE`, `WORLD`, `RECON`, `GEN`, `MEDIA`,
`CHECKPOINT`, `STORE`, `PACKAGE`, `SAVE`, `NATIVE`, `GM`, and `INTERNAL`.

## Severity and behavior

| Severity | Meaning |
|---|---|
| `info` | Expected state or completed recovery |
| `warning` | Safe degradation that does not violate a product invariant |
| `error` | Operation failed but application remains usable |
| `fatal` | Run/import cannot safely continue |

`retryable` is a machine decision, not advice to press Retry blindly. Terminal
configuration, integrity, persistence, and feasibility errors are never retried
automatically. Generation errors follow the selected execution policy. Mandatory
media failures may retry but must ultimately abort package publication.

## Configuration diagnostics

| Code | Condition | Behavior and recovery |
|---|---|---|
| `ST-CONFIG-001` | Configuration syntax is invalid | Abort; identify source line and correct the file. |
| `ST-CONFIG-002` | Unknown or duplicate key | Abort; remove or correct the key. |
| `ST-CONFIG-003` | Field value violates its type/range | Abort; show the field and accepted constraint. |
| `ST-CONFIG-004` | Cross-field invariant fails | Abort; explain the conflicting fields. |
| `ST-CONFIG-005` | Resume changes a locked semantic field | Reject resume; restore original configuration or begin a new run. |
| `ST-CONFIG-006` | Prompt/profile cannot resolve exactly | Abort; install/restore the registered prompt assets. |

## Model diagnostics

| Code | Condition | Behavior and recovery |
|---|---|---|
| `ST-MODEL-001` | Required model is missing | Abort/setup blocked; perform the explicit local download. |
| `ST-MODEL-002` | Checksum mismatch | Quarantine temporary download; download the registered model again. |
| `ST-MODEL-003` | Unsupported model format or capability | Abort; select a compatible registry entry. |
| `ST-MODEL-004` | License evidence is absent | Release blocked; complete model allowlist review. |
| `ST-MODEL-005` | Download interrupted | Preserve resumable temporary state where safe; retry explicitly. |
| `ST-MODEL-006` | Backend cannot load verified model | Abort current operation; inspect native/backend detail and resource profile. |

## Resource and storage diagnostics

| Code | Condition | Behavior and recovery |
|---|---|---|
| `ST-RESOURCE-001` | Predicted memory use exceeds safe profile | Abort before model load; lower concurrency or select a measured model profile. |
| `ST-RESOURCE-002` | Insufficient disk for work plus publication | Abort before generation/import; free space or choose another local location. |
| `ST-RESOURCE-003` | Runtime allocation fails | Cancel safely, unload models, preserve committed checkpoints, then resume with a safe profile. |
| `ST-STORE-001` | Atomic artifact write fails | Abort the dependent stage; preserve the previous committed artifact. |
| `ST-STORE-002` | Artifact hash differs from recorded metadata | Mark invalid; regenerate the artifact and dependants. |
| `ST-STORE-003` | Unsafe path or symlink escape | Abort as a security failure; choose a safe project path. |

## World and reconciliation diagnostics

| Code | Condition | Behavior and recovery |
|---|---|---|
| `ST-WORLD-001` | Physical-world invariant fails | Abort world stage; retain diagnostic seed and invariant details. |
| `ST-WORLD-002` | History references missing/invalid entity | Abort history stage; repair generator logic, not narrative output. |
| `ST-WORLD-003` | Determinism fixture diverges | Block release; compare engine, seed plan, and canonical serializer versions. |
| `ST-RECON-001` | Bible contradicts immutable procedural fact | Retry/regenerate Bible within policy; never mutate the procedural fact. |
| `ST-RECON-002` | Required procedural domain is omitted from Bible | Retry/regenerate; abort when policy is exhausted. |
| `ST-RECON-003` | Reconciliation cannot complete | Abort the run with conflict IDs and bounded evidence. |

## Narrative and media diagnostics

| Code | Condition | Behavior and recovery |
|---|---|---|
| `ST-GEN-001` | Backend generation failed transiently | Retry only according to execution policy. |
| `ST-GEN-002` | Output is not syntactically parseable | Retry with structured validation feedback; abort when exhausted. |
| `ST-GEN-003` | Output violates schema/domain contract | Retry affected item/step; never commit invalid output. |
| `ST-GEN-004` | Narrative references unavailable world entity | Regenerate affected narrative and dependants. |
| `ST-MEDIA-001` | Full image missing/invalid | Retry node media; package publication remains blocked. |
| `ST-MEDIA-002` | Thumbnail missing/invalid | Regenerate thumbnail; package publication remains blocked. |
| `ST-MEDIA-003` | MIDI missing, corrupt, empty, or zero-duration | Retry/regenerate track; package publication remains blocked. |
| `ST-MEDIA-004` | Media dimensions/profile mismatch | Regenerate with frozen profile; do not normalize corrupt source silently. |

## Checkpoint diagnostics

| Code | Condition | Behavior and recovery |
|---|---|---|
| `ST-CHECKPOINT-001` | Checkpoint is absent | Start a new run; do not claim resume. |
| `ST-CHECKPOINT-002` | Run fingerprint mismatch | Reject resume; explain changed model, prompt, schema, config, or code identity. |
| `ST-CHECKPOINT-003` | Artifact/checkpoint hash mismatch | Reconcile and regenerate affected dependency closure. |
| `ST-CHECKPOINT-004` | Checkpoint is corrupt/incomplete | Restore last valid atomic generation if available; otherwise start new run. |
| `ST-CHECKPOINT-005` | Resume dependency graph is inconsistent | Reject unsafe resume and preserve evidence for diagnosis. |

## Package diagnostics

| Code | Condition | Behavior and recovery |
|---|---|---|
| `ST-PACKAGE-001` | Invalid ZIP structure, traversal, link, or forbidden entry | Reject without extraction outside the sandbox. |
| `ST-PACKAGE-002` | Manifest/schema version unsupported | Reject; install a Player supporting the frozen v2 version. |
| `ST-PACKAGE-003` | Inventory entry missing, extra, or duplicated | Reject package. |
| `ST-PACKAGE-004` | Content hash mismatch | Reject as corrupt or tampered. |
| `ST-PACKAGE-005` | World/graph/domain validation fails | Reject package with bounded offending IDs. |
| `ST-PACKAGE-006` | Required node media is incomplete | Reject package. |
| `ST-PACKAGE-007` | Binary image or MIDI decode fails | Reject package. |
| `ST-PACKAGE-008` | Resource/safety limit exceeded during import | Reject safely; do not partially add to library. |
| `ST-PACKAGE-009` | Atomic package publication fails | Preserve prior output; run remains incomplete. |

## Save diagnostics

| Code | Condition | Behavior and recovery |
|---|---|---|
| `ST-SAVE-001` | Save package ID/hash does not match | Do not apply; select the matching package or begin a new playthrough. |
| `ST-SAVE-002` | Primary save is corrupt | Recover last valid atomic backup and disclose recovery. |
| `ST-SAVE-003` | No valid save generation exists | Preserve corrupt evidence; offer a new playthrough, never fabricate progress. |
| `ST-SAVE-004` | Save write fails | Keep prior committed save; warn before further navigation can lose progress. |

## Native Player and GM diagnostics

| Code | Condition | Behavior and recovery |
|---|---|---|
| `ST-NATIVE-001` | Native model/parser initialization fails | Disable affected action, preserve reading where safe, offer local diagnostic. |
| `ST-NATIVE-002` | Platform lacks required capability/storage | Explain requirement before download/import. |
| `ST-GM-001` | Reveal filter rejects requested knowledge | Answer only from allowed knowledge; this is not a backend retry. |
| `ST-GM-002` | GM model unavailable | Preserve reading; direct user to explicit model setup. |
| `ST-GM-003` | Chunk generation interrupted | Preserve committed chunks and discard incomplete chunk. |
| `ST-GM-004` | Chunk sequence/persistence mismatch | Stop response, restore committed transcript, and report diagnostic. |

## Internal faults

`ST-INTERNAL-001` represents an unexpected invariant or unclassified exception.
It is not a substitute for cataloging known failures. It aborts the affected
operation safely, emits a redacted local diagnostic, and is never automatically
retried unless a narrower typed cause is established.

## Logging and privacy

Diagnostics may record version IDs, hashes, seeds, timings, stable entity IDs,
bounded validation errors, and redacted local paths. They must not record full GM
prompts containing unrevealed knowledge, private absolute path components, model
download credentials, or unnecessary generated prose. Nothing is transmitted.

## UI presentation

Show the stable code, localized summary, consequence, and one primary recovery
action. Technical details are expandable and copyable. Screen readers announce
the summary once and place focus on the failing field or recovery action. Never
use color alone to distinguish warning, error, or fatal state.

## Tests and maintenance

- Every raised public diagnostic code exists in the typed catalog.
- Every catalog code has CLI, launcher, Android, and iOS conceptual mappings where
  applicable.
- Retry behavior is tested from catalog metadata.
- Messages and details pass redaction tests.
- Package and save failures leave prior user data unchanged.
- Unknown internal exceptions map to `ST-INTERNAL-001` and retain their local cause.
- Generated documentation is checked for drift in CI.

Adding or changing a code requires catalog, API, test-fixture, localization, and
recovery-documentation updates in the same change.

