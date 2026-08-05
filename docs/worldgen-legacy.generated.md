# Legacy Worldgen Compatibility Inventory

The following compatibility API remains after the completed worldgen rewrite.
Its removal is tracked only by `roadmap.md` P9.WG1:

| Legacy symbol | Definition | Production callers | Disposition |
|---|---|---|---|
| `generate_world` | `src/worldgen/generator.py` | `ProceduralWorldStep` | Deprecated; replace with `WorldStageRunner` |
| `WorldSnapshot` | `src/worldgen/models.py` | generator, adapter, compatibility step | Replace with separate immutable domain artifacts |
| `world_snapshot_to_context` | `src/worldgen/adapter.py` | `WorldBuilder` compatibility path | Remove after Bible consumes world artifact repository |
| `ProceduralWorldStep` | `src/worldgen/step.py` | compatibility tests only | Replace with declarative world stages |

Architecture tests may permit these imports only in the listed compatibility
modules and legacy characterization tests. New production modules use
`WorldSpec`, `WorldStage`, `WorldArtifact`, `GridChunk`, and
`WorldArtifactRepository`.
