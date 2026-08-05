# Rewrite Phase 5: Narrative Graph, Mandatory Media, and GM Knowledge

## Mission

Rewrite story, graph, media, and indexing around v2 world references. Produce a
complete narrative where every node has a valid full PNG, thumbnail, and
authoritative structured score with a positive-duration derived MIDI. Build a
complete reveal-gated knowledge index. Phase 6 implements package assembly and
executable schemas for the binding `package-v2.md` target.

## Entry state audit

| Current area | Disposition | Gap |
|---|---|---|
| `story_writer.py` | Rewrite inputs/output | Uses Bible without full world/reconciliation provenance |
| `game_designer.py` | Rewrite node contract | v1 IDs/media references and world travel validation are insufficient |
| `image_generator_step.py` | Rewrite persistence/policy | Quarantine permits incomplete batches and media commit is not fully crash-consistent |
| `music_generator_step.py` | Rewrite persistence/policy | Same; MIDI validation is insufficient |
| `pipeline/batch.py` | Rewrite item result/retry | String quarantines and path-existence resume are unsafe |
| `storage/indexer.py` | Replace index model | Does not cover full procedural/history knowledge contract |
| graph/story/style/gm schemas | Keep v1; develop v2 candidates | Freeze waits for Phase 6 |

## Action plan

- [ ] **P5.1 (M, depends Phase 4):** Define pre-freeze v2 story, graph, choice,
  flag, ending, media intent, and knowledge entry models with world IDs.
- [ ] **P5.2 (L, depends P5.1):** Rewrite Story Writer projections/prompts to use
  world, accepted Bible, and reconciliation report; retain outline/chapter
  checkpoints with dependency IDs.
- [ ] **P5.3 (XL, depends P5.2):** Rewrite Game Designer topology/node pipeline;
  validate world location containment, route/travel feasibility, entity state,
  flags, reachability, endings, and causal continuity.
- [ ] **P5.4 (M, depends P5.3):** Define per-node media contract: one image
  prompt, thumbnail derivation, music intent, and domain-separated seeds.
- [ ] **P5.5 (L, depends Phase 1):** Rewrite `BatchScheduler` with structured
  attempts/errors, policy-driven retry, terminal error propagation, and a typed
  completion callback.
- [ ] **P5.6 (L, depends P5.4,P5.5):** Generate each image to a temporary file,
  decode/size-validate it, atomically publish, hash, then checkpoint.
- [ ] **P5.7 (M, depends P5.6):** Derive thumbnail from the accepted full image,
  decode/size-validate, atomically publish, hash, and link provenance.
- [ ] **P5.8 (L, depends P5.4,P5.5):** Generate and validate an authoritative
  structured score, derive SMF Type 1/960 PPQ MIDI to a temporary file,
  parse it, require events and positive duration, atomically publish, hash, then
  checkpoint.
- [ ] **P5.9 (M, depends P5.6-P5.8):** Replace quarantine-as-product behavior:
  retries may be recorded, but any missing node asset makes the phase fail.
- [ ] **P5.10 (M, depends P5.5-P5.8):** Resume only verified files whose hash,
  seed, producer fingerprint, and dependencies match.
- [ ] **P5.11 (XL, depends P5.1-P5.3):** Replace GM indexer with complete world,
  history, Bible, story, and graph indexing; every entry carries source IDs and
  `reveal_after_nodes`.
- [ ] **P5.12 (M, depends P5.11):** Implement a platform-neutral reference
  eligibility function based only on visited nodes and shared normalization.
- [ ] **P5.13 (M, depends P5.1-P5.12):** Generate provisional artifact inventory
  and coverage report for Phase 6 without emitting a product package.

## Integrated `src/worldgen` rewrite work

Phase 5 absorbs worldgen rewrite WP7 and the opportunity/index portion of WP8.

- [ ] **P5.WG1 (L, depends Phase 3):** Generate deterministic factual story
  opportunities from unresolved pressures, participants, routes, resources,
  history, beliefs, and revealable facts; opportunities may not introduce facts.
- [ ] **P5.WG2 (M, depends P5.WG1,P5.1):** Require story/node location and route
  choices to reference feasible world opportunities and authoritative entity IDs.
- [ ] **P5.WG3 (XL, depends P5.WG2):** Generate a local 3D map for every
  registered site from macro terrain, geology, water, climate, routes,
  ownership, culture, technology, and event history.
- [ ] **P5.WG4 (L, depends P5.WG3):** Add strata, connected/sealed caves,
  deposits, aquifers, water/magma, heat, structural support, legal vertical
  movement, roads, parcels, buildings, workshops, stockpiles, and event scars.
- [ ] **P5.WG5 (M, depends P5.WG3,P5.WG4):** Validate macro/local consistency,
  path connectivity, fluid/heat conservation, support/collapse determinism, and
  site-specific resume equivalence.
- [ ] **P5.WG6 (M, depends P5.WG1-P5.WG5,P5.11):** Extend the complete GM/fact
  indexes with local-map facts, opportunity sources, incoming/outgoing references,
  and reveal metadata without omitting unused world data.

Local map generation is mandatory for every registered site, including sites not
referenced by narrative. Exhausted bounded retries abort the run rather than
removing the site or publishing an incomplete world.

## Target code example

```python
@dataclass(frozen=True)
class NodeMedia:
    node_id: str
    image: ArtifactRef
    thumbnail: ArtifactRef
    score: ArtifactRef
    midi: ArtifactRef


def require_complete_media(nodes: Sequence[GraphNode], media: Mapping[str, NodeMedia]) -> None:
    missing = sorted(node.node_id for node in nodes if node.node_id not in media)
    if missing:
        raise PackageValidationError(
            code="MEDIA_COVERAGE_INCOMPLETE",
            details={"missing_nodes": missing},
        )
```

```python
def revealed(entry: KnowledgeEntry, visited: frozenset[str]) -> bool:
    required = frozenset(entry.reveal_after_nodes)
    return not required or required.issubset(visited)
```

## File operations

Rewrite Story Writer, Game Designer, graph validators, media steps,
`pipeline/batch.py`, indexer, and their tests. Add shared knowledge-normalization
fixtures and media validators. Keep old schemas/packager only until Phase 6.

## Focused tests

- Story/graph world reference and route feasibility
- Graph topology, flags, conditional text, and endings
- Per-node seed and worker-count determinism
- Exact retry and terminal failure behavior
- Crash windows around media rename/checkpoint
- Corrupt/wrong-size PNG and thumbnail
- Invalid score, score/MIDI mismatch, corrupt/empty/zero-duration MIDI, wrong
  SMF type/PPQ, invalid loop markers, forbidden SysEx/programs
- Mandatory 100% node coverage
- Complete GM index source coverage
- Visited-node reveal sentinel tests

## Required commands at phase exit

```bash
.venv/bin/pytest -q tests/test_story_writer_v2.py tests/test_game_designer_v2.py
.venv/bin/pytest -q tests/test_batch_scheduler_v2.py tests/test_media_atomicity.py
.venv/bin/pytest -q tests/test_binary_media.py tests/test_media_coverage.py
.venv/bin/pytest -q tests/test_gm_index_v2.py tests/test_spoiler_contract.py
.venv/bin/python -m src.cli generate-narrative \
  --world tmp/world-phase3 --bible tmp/world-phase4/bible.json \
  --output tmp/world-phase5
.venv/bin/python -m src.cli validate-project tmp/world-phase5
```

## Exit checklist

- [ ] Story and graph resolve authoritative world IDs.
- [ ] Travel and chronology are validated.
- [ ] Every node has three verified media artifacts.
- [ ] Worker order and resume do not change canonical output.
- [ ] No partial-media success state exists.
- [ ] GM index covers complete knowledge and strict visited-node reveals.

## Phase 6 handoff

Phase 6 receives stable world and narrative domain shapes, complete verified
media, and a provisional inventory. It freezes schemas and publishes v2.
