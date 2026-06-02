from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path


MAX_EVENT_FILE_BYTES = 64 * 1024 * 1024


def rotate_file(path: Path, max_file_bytes: int = MAX_EVENT_FILE_BYTES) -> bool:
    if not path.exists() or path.stat().st_size < max_file_bytes:
        return False
    archive_dir = path.parent / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    archive_path = archive_dir / f"{path.stem}-{stamp}{path.suffix}"
    path.replace(archive_path)
    return True
