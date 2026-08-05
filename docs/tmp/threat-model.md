# StoryTeller Threat Model

## Scope

StoryTeller is local-first but still processes untrusted packages, downloaded
models, generated content, native libraries, and user questions. This model
covers Forge, v2 archives, native Players, local saves, GM inference, and the
thin launcher. It excludes a cloud service because none exists.

## Security goals

- Imported packages cannot write outside staging/library storage.
- Packages cannot execute code or install models.
- Model downloads are the intended immutable publisher artifacts.
- Immutable story content cannot be modified by reading or saving.
- Saves and conversations stay app-private and local.
- Unrevealed knowledge cannot reach the GM prompt.
- Logs/events do not leak hidden lore or full conversations by default.
- Corruption never becomes a trusted checkpoint or published package.
- Cancellation and crashes leave recoverable, internally consistent state.

## Assets

- Procedural and narrative intellectual content
- Package identity, hashes, and provenance
- Local model files and notices
- Reader progress, choices, bookmarks, and GM history
- Hidden/unrevealed story knowledge
- Device storage, memory, battery, and availability
- Native process integrity

## Trust boundaries

```text
Internet/model host -> model downloader -> temporary model -> verified model

External .story -> preflight -> private staging -> acceptance -> library

GUI input -> validated argv -> Forge child -> versioned JSONL -> GUI rendering

Complete GM index -> visited-node filter -> prompt -> native model -> chunks

Pipeline candidate -> validators -> atomic artifact -> checkpoint
```

Everything left of a validation boundary is untrusted.

## Threats and mitigations

### Malicious ZIP paths

**Threats:** traversal, absolute paths, backslashes, Unicode ambiguity, duplicate
normalized names, symlinks, device names, case collisions.

**Mitigations:** validate raw central-directory names before extraction; reject
links and duplicates; normalize only for comparison; allow declared relative
UTF-8 `/` paths; extract through safe file descriptors into private staging.

### Resource exhaustion

**Threats:** ZIP bombs, excessive entries, giant JSON, deep nesting, huge images,
MIDI parser abuse, enormous history indexes.

**Mitigations:** no arbitrary product-level package-size ceiling; require declared
entry and total uncompressed sizes, sufficient free storage before extraction,
compression-ratio/amplification checks, entry-count limits, streaming hash/parse
where possible, JSON nesting limits, bounded image dimensions, and parser
time/memory budgets. Phase 6 freezes shared numeric security thresholds against
the adversarial corpus without treating a merely large valid world as malicious.

### Integrity and provenance confusion

**Threats:** missing/changed files, manifest lying about hashes, broken/cyclic
dependencies, content ID collision, operational data included in identity.

**Mitigations:** SHA-256 each artifact and ZIP; recompute canonical inventory;
validate provenance DAG; content-derived IDs; canonical serialization; separate
operational logs from package identity.

### Unsafe resume

**Threats:** checkpoint points at missing, replaced, partial, or out-of-run file;
changed dependency is reused; crash occurs between file and DB commit.

**Mitigations:** confined canonical paths; temporary write/fsync/rename before
checkpoint; resume re-hashes and validates file, dependencies, and producer
fingerprint; downstream DAG invalidation; crash-window fault tests.

### Model supply chain

**Threats:** poisoned/tampered model, wrong revision, malicious redirect, partial
download treated as complete, license substitution.

**Mitigations:** release allowlist binds source, immutable revision, filename,
size, SHA-256, license revision, and role; explicit user consent; temporary path;
resume validation; atomic install; no model accepted from `.story`.

SHA-256 proves equality to the allowlisted artifact, not that the publisher is
benign. Model review and source governance remain release responsibilities.

### Native inference and parser safety

**Threats:** memory corruption in llama.cpp, ZIP/image/MIDI libraries, JNI/C
bridges; use-after-free during cancellation; malformed model metadata.

**Mitigations:** pin reviewed dependency revisions; minimize bridge surface;
sanitize lengths/indices; lifecycle state machines; platform sanitizers in test;
fuzz parsers and native entry points; unload on cancellation/background pressure.

### Spoiler leakage

**Threats:** hidden entry enters candidates, prompt, logs, prior conversation, or
error diagnostics; model infers secret from unfiltered complete context.

**Mitigations:** visited-node eligibility before prompt assembly; source-ID
reference implementation and cross-platform scenarios; sentinel tests at every
boundary; do not log full prompts; history itself passes reveal-safe assembly.

### Save tampering and mismatch

**Threats:** save applied to different package, invalid flags/nodes, external
modification, partial write, path collision between stories.

**Mitigations:** app-private storage; story ID plus package content hash; schema
and graph validation; atomic writes; isolate mismatch/corruption; per-story
directory derived through safe encoding.

### Launcher injection

**Threats:** title/path becomes shell syntax; malicious event text controls UI;
GUI loads backend directly; cancellation kills unrelated process.

**Mitigations:** argv array without shell; schema/version/size-limited JSONL
parser; escape UI text; keep child handle/run ID; no generation imports; process
ownership checks.

### Privacy leakage

**Threats:** analytics SDK, crash uploader, background networking, model host sees
more than download request, diagnostic export includes conversations.

**Mitigations:** no tracking SDK; network-blocked tests; explicit downloader-only
network capability; local logs omit questions/prompts; user-reviewed explicit
export; platform privacy/permission audit.

### Harmful generated content

**Threats:** prohibited sexual/exploitative/hateful/deceptive content, real-person
abuse, self-harm encouragement, store-policy violations.

**Mitigations:** mature profile disclosure and rating; local generation safety
rules; prohibited-content tests; local flag/export control; model/license/store
review. Offline architecture does not remove developer responsibility.

## Security requirements by phase

| Phase | Required security outcome |
|---:|---|
| 1 | Typed errors/events, path ownership, cancellation contract |
| 2-3 | Deterministic bounds/invariants and resource-aware world simulation |
| 4-5 | Reconciliation, binary validation, strict reveal reference logic |
| 6 | Safe ZIP, limits, provenance, resume reconciliation, v2 corpus/fuzzing |
| 7 | Staged native import, immutable library, app-private atomic saves |
| 8 | Verified model download, native lifecycle, spoiler boundary, safe GUI argv |
| 9 | Full fuzzing, dependency audit, offline/privacy evidence, release sign-off |

## Required security tests

- ZIP traversal/link/duplicate/collision/bomb corpus
- JSON depth/size/non-finite/duplicate-ID corpus
- PNG/MIDI malformed and resource-bound corpus
- Checkpoint crash windows and replaced-file cases
- Provenance cycles, missing dependencies, and hash substitution
- Downloader redirect, resume, bad hash, disk-full, and cancellation
- Native lifecycle stress and sanitizer runs
- Spoiler sentinel through retrieval, prompt, log, output, and history
- GUI argument/event fuzzing
- Network-blocked full post-download workflows

## Residual risks

- Local models may produce unwanted content despite controls.
- SHA-256 integrity does not provide author authenticity.
- Native inference/parser dependencies may contain undiscovered vulnerabilities.
- Very large valid user-generated packages may exhaust device storage by choice.
- Same-machine model determinism may change when native runtime revisions change;
  producer fingerprints and release records must expose this.

Release acceptance requires an explicit review of residual risks and mitigations.
