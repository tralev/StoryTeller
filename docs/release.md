# StoryTeller Target Release Process

## Purpose

This process releases free offline Forge/launcher and Android/iOS Players with a
frozen `.story` v2 contract. A release is evidence-driven: source presence or
mock-only success is insufficient.

## Release roles

One person may hold multiple roles, but each sign-off is explicit:

- Release owner: version, schedule, artifact inventory, final decision
- Forge owner: generation, packaging, determinism, desktop builds
- Android/iOS owners: native builds, scenarios, devices, stores
- Security/privacy owner: threat-model and data-flow evidence
- Model/license owner: allowlist, terms, checksums, notices
- Content/accessibility reviewer: mature content, quality, VoiceOver/TalkBack

## Version inputs

Freeze:

- Git commit and clean source tree
- Application and package versions
- JSON Schemas and schema hashes
- Prompt files and hashes
- Algorithm versions
- Model allowlist revisions/checksums/licenses
- Build toolchains and dependency lockfiles
- Shared scenario/fixture catalog
- Compliance-policy review date

No build reads a floating model revision or unpinned dependency.

## Model allowlist

Each model entry includes role, publisher, repository, immutable revision,
filename, byte size, SHA-256, quantization, context, expected RAM, license URL
and revision, notices, approved uses, and review date. A model change requires
new real-model evidence even if the application version is unchanged.

## Pre-release gates

### Documentation and contracts

- Frozen v2 schemas, shared fixtures, all validators, and `package-v2.md` agree.
- CLI help, pipeline table, archive paths, and scenario docs are generated and
  drift-free.
- Phase roadmap completion claims match retained verification evidence.
- Privacy, support, licenses, accessibility, and mature-content disclosures are
  final and reachable.

### Automated verification

```bash
./scripts/verify_release.sh --release-candidate
.venv/bin/mypy src scripts tests
.venv/bin/pytest -q -m "not integration"
.venv/bin/pytest -q -m integration --run-models
.venv/bin/pytest -q -m determinism
.venv/bin/pytest -q -m security
./scripts/build_all_desktop.sh
./scripts/test_wine.sh tmp/packages/storyteller-launcher.exe
./droid/gradlew -p droid testDebugUnitTest connectedDebugAndroidTest bundleRelease
xcodebuild -scheme StoryTeller -project ios/StoryTeller.xcodeproj \
  -derivedDataPath tmp/DerivedData test archive
.venv/bin/python scripts/verify_cross_platform_scenarios.py --release
.venv/bin/python scripts/check_docs_drift.py
```

Every wrapper prints subcommands, writes a machine-readable summary, and fails
on a skipped required gate.

### Real generation

Run a complete release-model generation and retain:

- Run specification and hash
- Code/config/prompt/schema/model hashes
- Environment/toolchain/reproducibility profile
- Model load/unload order
- Duration and peak memory
- Events and redacted diagnostics
- Internal artifact hashes and canonical package `content_hash` (never ZIP bytes)
- Package acceptance report

Interrupt a comparable run at controlled boundaries, resume it, and prove
canonical equivalence to uninterrupted output.

### Cross-platform acceptance

- Import the production package on physical Android and iOS.
- Run every shared scenario on Python, Android, and iOS.
- Verify graph outcomes, exact media, saves, v1 rejection, and spoiler sentinels.
- Download/verify/load the approved GM model.
- Block networking and test reading, restart, saves, history, and GM.
- Measure first chunk, throughput, RAM, storage, battery, and thermal behavior.

### Human review

- Procedural plausibility and map consistency
- Historical causality and final-state agreement
- Bible reconciliation
- Narrative coherence and meaningful choices/endings
- Image consistency and non-spoiling alternative text
- MIDI mood/loop/volume behavior
- GM accuracy, character, persistence, cancellation, and spoiler isolation
- Mature/prohibited content review
- VoiceOver, TalkBack, text scaling, contrast, motion, and audio controls

## Desktop artifacts

Build Forge and thin launcher for supported Windows, Linux, and macOS targets.
Test native Windows plus Wine. Verify clean install/start, model location,
generation form, JSONL progress, cancel/resume, final path, validation, and
uninstall/data-retention behavior.

Apply platform signing/notarization where distribution requires it. Package
third-party notices without bundling model weights.

## Mobile artifacts

- Android: signed release bundle/APK as required, Play declarations, Data Safety,
  content rating, AI disclosure, privacy/support URLs, first-launch downloader.
- iOS: archive, signing, App Store metadata/privacy labels, age rating, AI/mature
  disclosure, privacy/support URLs, first-launch downloader.

Both stores receive equivalent product claims. Do not claim cloud features,
accounts, telemetry, or v1 support.

## Security and privacy sign-off

- Threat-model requirements and fuzz/security suite pass.
- Package/import parsers enforce frozen limits.
- Model downloader uses allowlist and checksum.
- Dependency/native bridge review is complete.
- Post-download network-blocked evidence passes.
- Platform permissions/SDKs match the no-collection privacy statement.
- Logs and exports are reviewed for hidden lore and conversation leakage.

## Compliance sign-off

Re-check current Apple/Google policies and every model/dependency license. Store
links, dates, reviewer, declarations, notices, and unresolved risks in the
release record. Time-sensitive claims are never copied forward without review.

## Release record

```yaml
release: "2.0.0"
git_commit: "<sha>"
package_version: 2
schemas_sha256: "<sha>"
scenario_catalog_sha256: "<sha>"
models: {}
builds:
  windows: {sha256: "<sha>", smoke: true, wine: true}
  linux: {sha256: "<sha>", smoke: true}
  macos: {sha256: "<sha>", smoke: true, notarized: true}
  android: {sha256: "<sha>", physical: true}
  ios: {sha256: "<sha>", physical: true}
generation:
  content_hash: "<sha>"
  resume_equivalent: true
privacy_offline_verified: true
accessibility_verified: true
compliance_reviewed_at: "YYYY-MM-DD"
approvals: {}
```

## Publication

1. Tag the reviewed commit through the normal human-controlled release process.
2. Build only from the tag in a recorded environment.
3. Verify published artifact hashes against the release record.
4. Publish desktop artifacts and notices.
5. Submit mobile artifacts with accurate metadata.
6. Preserve the fixture package, logs, reports, internal-member hashes, and
   canonical package `content_hash`; do not create a ZIP-container hash.

This document does not authorize an automated agent to push, tag, submit a
store build, or publish a release.

## Rollback and incident response

- Remove or pause affected distribution when integrity/privacy/content risk is
  credible.
- Preserve evidence and identify affected app/model/package versions.
- Rotate the model allowlist or application build; never silently accept a new
  checksum for the same release.
- Package v2 content remains immutable. Corrected stories receive new identity.
- Communicate local-data effects accurately; no server-side save recovery exists.
- Add regression tests and update the threat/decision records before rerelease.

## Completion checklist

- [ ] All required automated commands pass without skipped release gates.
- [ ] Real generation and resume equivalence evidence exists.
- [ ] Production package imports on physical Android and iOS.
- [ ] Offline GM and strict spoiler evidence passes.
- [ ] Security, privacy, model license, store, and accessibility reviews are dated.
- [ ] All distributed hashes match the release record.
- [ ] Documentation and current roadmap match verified release behavior.
