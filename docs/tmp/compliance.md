# StoryTeller Target Compliance and Licensing

## Status and scope

This future-state checklist is not legal advice. Store rules and model terms can
change; release owners must re-check the linked primary sources before every
submission. Delivery status belongs in evidence-backed phase roadmap checkboxes.

StoryTeller targets free distribution on the Apple App Store and Google Play.
It processes mature dark-fantasy content and runs a generative Game Master on
the device. It has no accounts, ads, telemetry, cloud saves, cloud inference, or
remote StoryTeller content service.

## Privacy target

After explicit model download, Forge and Player work completely offline.

| Data | Location | Network use |
|---|---|---|
| Generated worlds and packages | User-selected desktop storage | None |
| Imported package content | App-private mobile storage | None |
| Reading progress and bookmarks | App-private mobile storage | None |
| GM questions and responses | App-private mobile storage | None |
| Models | User/device model directory | Download only |
| Diagnostics | Local logs | Shared only by explicit user action |

The apps request no account identity and ship no analytics or advertising SDK.
The privacy policy must nevertheless explain model downloads, local storage,
retention, deletion, file import/export, and the absence of collection. Apple
requires an accessible privacy-policy link for App Store apps; see the
[App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/).

## Model distribution policy

Models are not bundled with the free applications. The user explicitly starts a
download from the model publisher or an approved mirror. The downloader must:

1. Show model name, publisher, source, size, license link, and required notices.
2. Obtain user confirmation and allow cancellation/resume.
3. Download to a temporary path.
4. Verify a release-pinned SHA-256 digest.
5. Atomically publish the model only after verification.
6. Retain the exact license/notice text associated with that model version.

The model registry must not assume that a quantized derivative has identical
terms to its upstream model; verify both the upstream and distributor pages.

## Current candidate licenses

| Candidate | Published terms | Target action |
|---|---|---|
| Qwen2.5-7B-Instruct | [Apache 2.0](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct/blob/bb46c15ee4bb56c5b63245ef50fd7637234d6f75/LICENSE) | Preserve license/notice; verify GGUF distributor provenance |
| Phi-3.5-mini-instruct | [MIT](https://huggingface.co/microsoft/Phi-3.5-mini-instruct/blob/2fe192450127e6a83f7441aef6e3ca586c338b77/LICENSE) | Preserve copyright and license text |
| SDXL-Turbo | [Stability AI Community License](https://huggingface.co/stabilityai/sdxl-turbo/blob/ef0d007d296a24f621ab6d376e7055eb6116877b/LICENSE.md) | Re-evaluate revenue threshold, registration, attribution, AUP, and commercial terms before release |
| Llama 3.2 3B | Llama Community License from the selected official model release | Preserve required attribution/notice and confirm downloader terms before release |
| llama.cpp | Repository license plus third-party notices | Preserve license and notices for the embedded native library |

Model choice remains configurable, but “downloadable” does not mean
“redistributable” or “store-safe.” A release allowlist must bind repository,
revision, filename, SHA-256, license revision, intended role, and notices.

## Mature content policy

The product is intended for mature dark fantasy, including fictional violence,
horror, death, and disturbing themes. It must not target children and must not
generate prohibited sexual, exploitative, hateful, harassing, deceptive, or
real-person abuse content.

Required controls:

- An accurate mature-content rating and store questionnaire answers
- Clear AI-generated-content disclosure before import/GM use
- A content profile embedded in each package manifest
- Generation and GM safety rules enforced locally
- A local “flag response” control for GM output
- A privacy-preserving way for a user to export a flagged excerpt voluntarily
- No automatic upload of prompts, output, or reports
- A local reset/delete mechanism for GM history

Google states that generative-AI apps must prevent restricted content and must
provide in-app reporting/flagging without forcing users to leave the app; see
[Google Play's AI-generated content policy](https://support.google.com/googleplay/android-developer/answer/13985936?hl=en-GB)
and its [policy explanation](https://support.google.com/googleplay/android-developer/answer/14094294?hl=en-EN).
Because StoryTeller has no backend, a release review must confirm whether a fully
local flag/export workflow satisfies the then-current requirement. Do not add
telemetry silently to solve this tension.

Apple's safety and objectionable-content rules remain applicable even when
generation is local. Its [App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/)
are the release authority; do not assume that an entertainment disclaimer cures
otherwise prohibited content.

## Required user disclosures

Before generation or GM model use, disclose:

- Content and media are generated by machine-learning models.
- Mature fictional material may be violent or disturbing.
- Models can produce incorrect or unwanted output.
- GM processing and conversation storage occur locally.
- Model download requires network access and substantial storage.
- Story packages can be large and have no Forge-enforced size ceiling.
- Deleting the app or local story data can permanently delete saves/history.

## Copyright and provenance

- Store exact model, prompt, schema, code, and configuration hashes per artifact.
- Preserve model and dependency notices outside generated story content.
- Do not claim copyright ownership or originality guarantees that local law does
  not support.
- Do not train on or redistribute imported `.story` packages.
- Generated packages should record their tool provenance without embedding the
  model binaries.
- The application must not imitate living artists through a product-level
  “in the style of” feature.

## Package and save security

- Treat every `.story` as untrusted input.
- Reject absolute paths, traversal, symlinks, undeclared files, excessive entry
  counts, decompression bombs, invalid hashes, corrupt media, and unsupported v1.
- Extract into a private staging directory and publish only after validation.
- Keep content read-only and local saves outside the package, keyed by story ID.
- Use platform data-protection facilities for save and GM history files.
- Do not execute scripts, HTML, native code, or model files from a package.
- SHA-256 provides integrity, not publisher authenticity; package signing is not
  a target requirement.

## Store submission checklist

### Both stores

- [ ] App is free and contains no ads, tracking, accounts, or cloud feature.
- [ ] Privacy policy and support contact are published and accessible in-app.
- [ ] AI and mature-content disclosures match actual behavior.
- [ ] Model-download source, checksum, size, license, cancellation, and deletion
  flows are tested.
- [ ] Local data inventory and deletion behavior are documented.
- [ ] Physical-device memory, storage, offline, and package-import tests pass.
- [ ] Third-party notice bundle is complete and revision-pinned.

### Apple

- [ ] App Store age-rating questionnaire reflects mature generated content.
- [ ] App Review notes explain local GM generation and first-launch model
  download.
- [ ] Privacy nutrition labels declare only data actually collected.
- [ ] Model download and offline behavior pass review without hidden code or
  executable content delivery.

### Google Play

- [ ] Content rating and generative-AI declarations are complete.
- [ ] Restricted-content prevention and in-app flagging satisfy current policy.
- [ ] Data Safety answers reflect no collection or sharing.
- [ ] Download behavior respects user choice, metered-network guidance, storage,
  cancellation, and cleanup.

## Release evidence

Every release retains a dated compliance record containing store-policy review
links, model/license revisions, third-party notices, privacy/data-flow review,
content-safety tests, package-security tests, and the final store declarations.
