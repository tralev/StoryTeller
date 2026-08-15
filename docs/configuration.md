# StoryTeller Target Configuration Reference

## Status

This is the target configuration contract. Typed run/world specifications and a
release model registry exist; the complete generated field/default/CLI reference
is still a planned drift gate. Examples here define required shape and semantics,
not a claim that every displayed launcher field exists.

## Goals

- One validated `RunSpec` controls a generation run.
- Unknown keys and ambiguous values fail before work starts.
- Effective configuration is serializable, hashable, and safe to record.
- CLI and thin GUI use the same parser and application service.
- Defaults support one continent and the complete mandatory pipeline.

## Precedence

Lowest to highest precedence:

1. schema defaults;
2. one optional project configuration file;
3. explicit CLI flags or GUI fields;
4. resume-locked values from the original run.

Environment variables are limited to documented machine-local paths and test
controls. They cannot silently override seed, world, prompts, policies, or model
identity. Unknown keys, duplicate aliases, and conflicting overrides are errors.

The effective configuration is materialized before execution and stored with the
run evidence. Secrets are redacted; normal offline generation requires no secret.

## Candidate configuration

```yaml
config_version: 2

run:
  seed: 184467
  output_directory: ./output
  resume: false

world:
  preset: standard
  continent_count: 1
  width: 1024
  height: 1024
  metres_per_world_cell: 8000
  history_years: 500
  civilization_count: 8
  surface_chunk_width: 256
  surface_chunk_height: 256
  local_site_width: 128
  local_site_height: 128
  local_z_levels: 32
  local_chunk_width: 32
  local_chunk_height: 32
  local_chunk_depth: 16
  snapshot_interval_years: 10
  retain_full_simulation: true

narrative:
  genre: mature_dark_fantasy
  locale: en
  prompt_profile: storyteller-v2

media:
  world_map_profile: png_rgba_srgb_4096
  region_map_profile: png_rgba_srgb_1024
  node_image_profile: png_rgba_srgb_1024
  thumbnail_profile: png_rgba_srgb_256
  music_profile: structured_score_v1_smf1_960ppq_gm1
  require_every_node: true

models:
  text: qwen-local
  image: sdxl-local
  gm: qwen-mobile

execution:
  text_workers: 1
  image_workers: 1
  music_workers: 1
  memory_budget_mib: 10240
  retry_profile: standard
  checkpoint: true

packaging:
  format: story-v2
  canonical: true
```

Fields whose values are product invariants—procedural generation, complete media,
full simulation retention, v2 packaging, local saves—may be visible for clarity
but cannot be disabled in a production profile.

## `RunSpec`

The parser converts configuration to a frozen typed `RunSpec`. It contains:

- canonical seed and derived seed plan;
- physical-world and history parameters;
- narrative and locale profile;
- exact prompt profile;
- exact model registry references;
- execution and retry policies;
- output and checkpoint locations;
- canonical v2 packaging profile.

Paths are resolved and validated before hashing but machine-specific absolute paths
are excluded from semantic reproducibility fingerprints. Model and prompt content
hashes are included.

## World controls

One continent is the default, not a hard limit. A preset expands to explicit
physical dimensions, scales, climate parameters, history duration, and population
budgets before the run begins. The effective expanded values are recorded.

Coordinates use the canonical world-cell-plus-scale model. Parameters must obey domain
constraints and resource feasibility. Forge aborts rather than secretly reducing
world fidelity or switching to a narrative-only mode.

There is no configured maximum `.story` file size. Forge still validates free disk
space and ZIP/resource safety before generation and publication.

## Model registry

Models are referenced by stable registry ID, never by an arbitrary user-facing
filename alone.

```yaml
models:
  qwen-local:
    capability: text_generation
    provider: llama_cpp
    path: ai_models/qwen/model.gguf
    sha256: "<sha256>"
    license_id: "<reviewed license ID>"
    context_tokens: 32768
    memory_profile: qwen-local-q4
```

Each entry declares provider, capabilities, local path, checksum, format,
compatible prompt/output profiles, license evidence, and measured resource profile.
Missing files and checksum mismatch fail before generation. Models are downloaded
only through explicit setup or first-launch consent flows; normal runs are offline.

## Execution policies

Retry profiles declare attempt counts, backoff, retryable categories, and terminal
categories. `max_retries` means retries after the first attempt. Configuration,
dependency, persistence, integrity, and resource-feasibility failures are terminal.
Independent generation failures may retry, but mandatory node media may not remain
quarantined at publication.

Worker counts are bounded by backend thread safety and measured memory profiles.
Planning rejects an unsafe combination instead of relying on operating-system
failure.

## Paths

- Project configuration may use paths relative to its own directory.
- Output, checkpoint, cache, and model roots are distinct.
- The output package is published atomically to the requested output directory.
- Caches are disposable and never authoritative.
- Checkpoints and local diagnostics are outside `.story` packages.
- Player saves are configured by each native app and remain outside packages.

Path traversal, symlink escape, device files, and a package path overlapping a
working directory are rejected.

## CLI mapping

Every CLI option maps to exactly one typed field. Expected principal commands:

```text
forge config validate --config project.yaml
forge config show-effective --config project.yaml
forge models verify --config project.yaml
forge generate --config project.yaml
forge resume --output DIR [--config project.yaml]
forge validate-package FILE.story [--json]
```

`show-effective` emits canonical redacted configuration and its semantic hash.
`generate` and the GUI call the same application service after validation.

## Validation sequence

1. Parse syntax with source locations.
2. Reject unknown and conflicting keys.
3. Apply documented defaults and overrides.
4. Validate typed fields and cross-field invariants.
5. Resolve prompt and model registries to exact hashes.
6. Validate paths, free disk, and resource feasibility.
7. Materialize frozen `RunSpec`, seed plan, and run fingerprint.

Errors use the stable diagnostic catalog in `diagnostics.md`.

## Generated reference requirements

CI must generate a field table from the settings schema containing
type, default, constraints, CLI mapping, restart/resume behavior, and sensitivity.
CI fails if generated output differs from the checked-in reference. Supported
models and benchmark profiles are generated from their registries in the same way.

The current world-generation portion is generated as
`world-controls.generated.md`. Every `WorldSpec` field must be classified as
either a `forge generate` integer option or a named fixed worldgen-1 invariant;
unclassified and multiply classified fields fail parser construction and tests.

## Tests

- Defaults resolve to one continent and all mandatory stages.
- Unknown fields and invalid enum values fail.
- Equivalent YAML and CLI inputs produce identical `RunSpec` hashes.
- Resume rejects changes to locked semantic fields.
- Paths do not affect canonical content unless their content identity changes.
- Unsafe worker/memory combinations fail before model loading.
- Missing or altered model/prompt files fail checksum verification.
- GUI and CLI produce the same effective configuration.
