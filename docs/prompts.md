# StoryTeller Target Prompt Contract

## Purpose and authority

This document defines how prompts are identified, versioned, resolved, rendered,
validated, and recorded. It is a future-state contract. Prompt text remains an
implementation asset, but its identity and provenance are part of reproducibility.

Frozen schemas and `package-v2.md` outrank a prompt: a prompt can request a valid
result, but it cannot redefine a domain or package contract.

## Principles

- Every production prompt has a stable ID and immutable semantic version.
- Published prompt content is never edited in place or silently deleted.
- Inputs and expected output are typed and validated.
- Prompt selection is configuration-driven, never an unrecorded backend default.
- Rendering is deterministic for the same template, ordered inputs, and renderer.
- Secrets, absolute private paths, and unrevealed Player knowledge never enter a
  prompt.
- A successful artifact records enough information to explain exactly which prompt
  produced it.

## Prompt identity

A prompt reference has three fields:

```json
{
  "id": "narrative.node_text",
  "version": "2.1.0",
  "sha256": "<64 lowercase hexadecimal characters>"
}
```

IDs use lowercase dotted names grouped by responsibility, for example:

- `world.bible`
- `world.reconciliation`
- `narrative.outline`
- `narrative.node_text`
- `media.image`
- `media.music_plan`
- `gm.response`

The version describes the prompt contract, not the model. The hash covers the
exact UTF-8 template bytes after newline normalization and before rendering.

## Version rules

| Change | Required version change |
|---|---|
| Wording only, with identical inputs and output contract | Patch |
| New optional input or compatible behavioral change | Minor |
| Required input, output schema, or semantic meaning changes | Major |

Once used by a committed artifact or release fixture, a prompt version is
immutable. Correction requires a new version. Deprecated versions remain
available while checkpoints, fixtures, or supported packages refer to them.

Removal is permitted only when no supported resume state, fixture, release, or
configuration can resolve the version. Removal is recorded as a decision and a
release note.

## Prompt asset layout

```text
prompts/
  registry.yaml
  world/
    bible/
      2.0.0.j2
  narrative/
    node_text/
      2.1.0.j2
  gm/
    response/
      2.0.0.j2
```

`registry.yaml` maps a prompt reference to its file, input model, output schema,
renderer version, compatible model capabilities, and lifecycle status. Paths are
repository-relative and cannot escape the prompt root.

## Typed input boundary

Each prompt declares one typed input model. Pipeline code constructs that model;
templates do not read `PipelineContext.state`, arbitrary dictionaries, environment
variables, or the filesystem.

```python
class NodeTextPromptInput(BaseModel):
    node_id: NodeId
    world_facts: tuple[WorldFact, ...]
    narrative_state: NarrativeState
    allowed_characters: tuple[CharacterId, ...]
    style: StyleProfile
    output_schema_version: str
```

Inputs use stable IDs and canonical ordering. The renderer rejects unknown fields,
missing fields, noncanonical ordering, and values exceeding declared budgets.

## Output contracts

Structured generation references a versioned JSON Schema. A backend response is
untrusted until it passes:

1. syntactic parsing;
2. schema validation;
3. domain validation;
4. cross-artifact reconciliation where applicable;
5. canonical normalization.

Validation feedback used for a retry is itself structured. It includes stable
codes and bounded context, not arbitrary stack traces or prior full outputs.

## Resolution

`RunSpec.prompt_profile` selects an immutable prompt-profile version. The profile
resolves every required prompt ID to an exact version and hash before generation
starts. Resolution fails if an ID is missing, a hash differs, the output schema is
unavailable, or the selected backend lacks a required capability.

The resolved profile becomes part of the run fingerprint. Resume rejects a
checkpoint if the resolved prompt set differs for any affected artifact.

No “latest” reference is allowed after `RunSpec` validation.

## Rendering and budgets

- UTF-8, LF newlines, and deterministic template settings are mandatory.
- Maps and sets are sorted canonically before rendering.
- Dates, numbers, coordinates, and units use canonical serializers.
- Each prompt declares input-token and output-token budgets.
- Budget overflow is a terminal planning/configuration diagnostic unless the step
  explicitly defines a deterministic chunking strategy.
- Truncating world facts or GM knowledge silently is forbidden.

## Game Master prompt isolation

The GM prompt accepts only knowledge returned by the strict reveal filter for the
current package and visited-node set. Filtering occurs before prompt assembly.
Logs may store IDs and hashes, but never unrevealed prompt content. A prompt
renderer cannot query the complete world or narrative repositories directly.

## Provenance record

Every prompt-produced artifact records:

```json
{
  "prompt": {
    "id": "narrative.node_text",
    "version": "2.1.0",
    "template_sha256": "<sha256>",
    "rendered_input_sha256": "<sha256>",
    "output_schema": "narrative-node@2.0.0"
  },
  "model": {
    "provider": "llama_cpp",
    "model_id": "<registry ID>",
    "file_sha256": "<sha256>"
  },
  "seed": 12345
}
```

Rendered prompt text need not be packaged. The local run evidence may retain it
when diagnostics policy allows; hashes and references are always retained.

## Tests and acceptance

- Registry entries resolve to existing files and schemas.
- Recorded template hashes match exact file content.
- Golden input renders byte-identically across supported Forge platforms.
- Unknown input fields and missing fields fail before backend invocation.
- Schema-invalid output cannot be committed.
- Deprecated versions remain resolvable for supported fixtures.
- Changing any resolved prompt invalidates dependent checkpoints.
- GM tests prove unrevealed facts are absent from the rendered prompt.

## Delivery ownership

Core generation prompt identity and provenance belong to the implemented Forge
pipeline. Phase 8 completes and audits streamed GM prompt isolation. Phase 9
generates drift evidence and records the final release prompt profile.
