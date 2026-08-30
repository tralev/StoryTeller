"""Catalog-wide canonical chunk-byte verification for physical dense grids."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .artifacts import GridChunk, WorldArtifactRepository
from .grid import DenseGridCatalog

PHYSICAL_GRID_CATALOG_KINDS = (
    "terrain_grid_catalog",
    "geology_grid_catalog",
    "hydrology_grid_catalog",
    "climate_grid_catalog",
    "soil_grid_catalog",
    "biome_grid_catalog",
    "resource_grid_catalog",
    "region_grid_catalog",
)


@dataclass(frozen=True)
class GridCatalogByteAudit:
    catalogs: int
    layers: int
    chunks: int


def _chunk_path(root: Path, layer: str, chunk_x: int, chunk_y: int) -> Path:
    return root / "chunks" / layer / f"{chunk_y:06d}_{chunk_x:06d}.grid"


def verify_catalog_chunk_bytes(
    first_root: str | Path,
    second_root: str | Path,
) -> GridCatalogByteAudit:
    """Prove all physical catalogs and canonical uncompressed chunks are byte-identical."""
    first = Path(first_root).resolve()
    second = Path(second_root).resolve()
    first_artifacts = WorldArtifactRepository(first / "artifacts")
    second_artifacts = WorldArtifactRepository(second / "artifacts")
    layer_count = 0
    chunk_count = 0
    for kind in PHYSICAL_GRID_CATALOG_KINDS:
        left_artifact = first_artifacts.load_verified(kind)
        right_artifact = second_artifacts.load_verified(kind)
        if left_artifact.artifact_id != right_artifact.artifact_id:
            raise ValueError(f"WG-GRID-BYTES: {kind} artifact mismatch")
        left = DenseGridCatalog.from_mapping(left_artifact.payload)
        right = DenseGridCatalog.from_mapping(right_artifact.payload)
        if left != right:
            raise ValueError(f"WG-GRID-BYTES: {kind} manifest mismatch")
        for manifest in left.manifests:
            layer_count += 1
            for descriptor in manifest.chunks:
                left_bytes = _chunk_path(
                    first,
                    manifest.layer,
                    descriptor.chunk_x,
                    descriptor.chunk_y,
                ).read_bytes()
                right_bytes = _chunk_path(
                    second,
                    manifest.layer,
                    descriptor.chunk_x,
                    descriptor.chunk_y,
                ).read_bytes()
                if left_bytes != right_bytes:
                    raise ValueError(f"WG-GRID-BYTES: {manifest.layer} byte mismatch")
                if hashlib.sha256(left_bytes).hexdigest() != descriptor.sha256:
                    raise ValueError(f"WG-GRID-BYTES: {manifest.layer} hash mismatch")
                chunk = GridChunk.decode(left_bytes)
                if (
                    chunk.layer != manifest.layer
                    or chunk.chunk_x != descriptor.chunk_x
                    or chunk.chunk_y != descriptor.chunk_y
                    or chunk.width != descriptor.width
                    or chunk.height != descriptor.height
                ):
                    raise ValueError(f"WG-GRID-BYTES: {manifest.layer} header mismatch")
                chunk_count += 1
    return GridCatalogByteAudit(len(PHYSICAL_GRID_CATALOG_KINDS), layer_count, chunk_count)
