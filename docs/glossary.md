# StoryTeller Glossary

This glossary defines target terminology. Current code may use older names until
the rewrite phases replace them.

## Product terms

**Forge**  
The local desktop generator, exposed through a CLI and later a thin GUI.

**Player**  
The native Android or iOS reader application.

**Story package / `.story`**  
An immutable ZIP archive conforming to package version 2.

**Playthrough**  
One local mutable reading state for a story package.

**Game Master (GM)**  
The on-device conversational model and retrieval flow used by a Player.

## World terms

**Authoritative fact**  
A physical, climatic, geographic, civilization, or simulated historical fact
produced by procedural generation. Narrative stages cannot modify it.

**Procedural world**  
The complete structured output of physical generation and historical simulation.

**World domain**  
One separately serialized concern such as terrain, hydrology, climate, regions,
civilizations, or history.

**World cell**  
The canonical integer `(x, y)` surface coordinate unit. Physical distance derives
from integer `metres_per_world_cell`. “Tile” is reserved for local 3D-map cells.

**Region**  
A stable-ID geographic grouping of authoritative cells with boundary and
adjacency data.

**Site**  
A stable-ID location contained by a region, such as a settlement or ruin.

**Local entity**  
A narrative-added building, street, cave, ruin, item, or minor character with a
valid authoritative container. It is not permitted to redefine major world data.

**Present year**  
The configured year where historical simulation stops and narrative present
begins.

**Event ledger**  
The complete ordered collection of causal historical events.

**Historical snapshot**  
A materialized simulation state tied to a precise ledger position. v2 stores one
at year 0, every ten years, and the final year, without duplicating the final
snapshot when it is already a ten-year boundary.

**Derived map**  
A rendered image based on structured coordinates. It is never authoritative.

## Narrative terms

**World Bible**  
Structured narrative enrichment of the immutable procedural world.

**Reconciliation**  
Mandatory deterministic validation of Bible claims against authoritative facts.

**Story**  
The linear narrative backbone created from the world and accepted Bible.

**Graph**  
The branching reader-facing nodes, choices, flags, conditions, and endings.

**Node**  
One playable graph scene with exactly one full image, thumbnail, authoritative
structured score, and derived MIDI track.

**Reveal rule**  
A set of graph nodes that must have been visited before a knowledge entry may be
provided to the GM.

## Architecture terms

**Interface / port**  
A capability contract required by core logic without reference to a concrete
engine or model.

**Backend / adapter**  
A concrete implementation of a port using an external library or model runtime.

**Model descriptor**  
Pinned metadata for a downloadable model: source, revision, filename, checksum,
license, role, quantization, context, and memory expectation.

**Model file**  
Downloaded inference weights. A model file is data, not a pipeline component.

**Pipeline step**  
One declared transformation from verified artifact dependencies to one artifact.

**Pipeline plan**  
The validated directed acyclic graph of steps, dependencies, model roles,
validators, checkpoints, and failure policies.

**Pipeline runner**  
The component that executes the plan and owns retries, resources, cancellation,
events, commits, and checkpoints.

**Application service**  
The use-case boundary that turns a generation request into a generation result.

**Validator**  
A side-effect-free gate returning structured issues. Deterministic validators
are mandatory; a model critic is optional and cannot waive errors.

## Artifact terms

**Artifact**  
A durable typed output such as terrain, Bible, graph, PNG, or MIDI.

**Artifact reference**  
The artifact ID, kind, canonical path, SHA-256, dependencies, and producer
fingerprint used to locate and verify an artifact.

**Artifact ID**  
A stable content-derived identifier. It contains no timestamp or local path.

**Canonical content**  
Bytes and metadata that define product identity and reproducibility.

**Operational metadata**  
Run-local data such as timestamps, duration, logs, RAM samples, retries, and
paths. It does not affect canonical identity.

**Content hash**  
The canonical hash of the declared artifact inventory.

**Package content hash**

SHA-256 derived from canonical paths and uncompressed bytes of declared files
inside the package. The ZIP container bytes are never hashed.

**Producer fingerprint**  
A hash of the code/algorithm, prompts, schemas, model bytes, and relevant
configuration that produced an artifact.

**Provenance DAG**  
The directed acyclic graph formed by artifact `depends_on` references.

## Reliability terms

**Atomic publication**  
Writing and validating a temporary file in the destination filesystem before an
atomic rename makes it visible.

**Checkpoint**  
Operational resume metadata pointing to an already committed artifact.

**Resume reconciliation**  
Verification of actual file bytes, path, schema/media validity, producer
fingerprint, and dependencies before reuse.

**Retry**  
Another attempt after the initial call. `max_retries` excludes the first attempt.

**Terminal failure**  
A configuration, dependency, resource, persistence, or integrity error that is
not automatically retried.

**Quarantine**  
An operational record for an independent failed attempt. It never permits a
final package with missing mandatory node media.

## Compatibility terms

**Package v1**  
The legacy narrative-first prototype format, unsupported by target Forge/Player.

**Package v2**  
The sole target product format, frozen in rewrite Phase 6.

**Internal schema upgrade**  
A migration of operational data such as the checkpoint database. This is not a
package migration and does not add v1 Player support.
