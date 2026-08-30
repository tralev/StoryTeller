"""Frozen PNG and score/MIDI binary-profile validation."""

from __future__ import annotations

import zipfile
from typing import Any, Mapping

from ...narrative.media import (
    FULL_SIZE,
    THUMB_SIZE,
    validate_midi,
    validate_png,
    validate_score,
)
from ...narrative.pipeline import _score_from_dict
from .common import JsonLoader, PackageV2Error


def validate_binary_media(
    archive: zipfile.ZipFile,
    manifest: Mapping[str, Any],
    load_json: JsonLoader,
) -> None:
    try:
        validate_png(archive.read("assets/maps/world.png"), (4096, 4096))
        for path in manifest["region_maps"].values():
            validate_png(archive.read(path), (1024, 1024))
    except (ValueError, KeyError, TypeError) as error:
        raise PackageV2Error(
            "PACKAGE_PNG_PROFILE", str(error), "assets/maps"
        ) from error

    for node, assets in manifest["node_assets"].items():
        try:
            validate_png(archive.read(assets["image"]), FULL_SIZE)
            validate_png(archive.read(assets["thumbnail"]), THUMB_SIZE)
            score_path = assets["score"]
            score = _score_from_dict(
                load_json(archive.read(score_path), score_path)
            )
            validate_score(score)
            validate_midi(archive.read(assets["midi"]), score)
        except (ValueError, KeyError, TypeError) as error:
            code = (
                "PACKAGE_PNG_PROFILE"
                if "PNG-" in str(error)
                else "PACKAGE_BINARY_MEDIA"
            )
            raise PackageV2Error(code, str(error), str(node)) from error
