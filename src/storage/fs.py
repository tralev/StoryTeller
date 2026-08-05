"""Atomic file helpers (Phase 5.6 O2).

JSON artifacts are written atomically by ArtifactStore (O1) and the final
.story archive by Packager (O5). Media outputs — PNG images, thumbnails,
and MIDI tracks — previously used direct ``write_bytes`` calls, which could
leave partially-written files on crash. These helpers make every media write
crash-safe: bytes go to a ``.tmp`` file in the same directory, then an atomic
rename publishes the file. Readers never observe a partial file, and a failed
write never clobbers the previous artifact.
"""

from __future__ import annotations

import os
from pathlib import Path


def atomic_write_bytes(
    path: str | Path,
    data: bytes,
    *,
    tmp_suffix: str = ".tmp",
) -> None:
    """Write bytes atomically: temp file in the target directory, then rename.

    Args:
        path: Destination path. Parent directories are created if missing.
        data: Bytes to write.
        tmp_suffix: Suffix for the temporary file. The temp file lives in
            the same directory as the target so ``os.replace`` is atomic
            (same filesystem).

    Raises:
        OSError: If the write fails. The temp file is removed and any
            pre-existing target file is left untouched.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + tmp_suffix)
    try:
        # Keep the write operation as a single replaceable seam for crash and
        # disk-full fault injection, then durably flush the completed temp file.
        tmp_path.write_bytes(data)
        descriptor = os.open(tmp_path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(tmp_path, path)
        try:
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except OSError:
            # Some filesystems/platforms do not permit directory fsync.
            pass
    except BaseException:
        # Clean up the partial temp file; never leave it behind.
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
