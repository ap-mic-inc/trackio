"""Disk usage of each project's local data, for the dashboard's Storage view."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from trackio import utils
from trackio.sqlite_storage import SQLiteStorage

CATEGORIES = ("database", "media", "files", "artifacts", "traces")


def _dir_usage(path: Path, exclude: Path | None = None) -> tuple[int, int]:
    total = count = 0
    if not path.is_dir():
        return total, count
    for root, dirs, names in os.walk(path):
        if exclude is not None:
            dirs[:] = [d for d in dirs if Path(root, d) != exclude]
        for name in names:
            try:
                stat = os.lstat(os.path.join(root, name))
            except OSError:
                continue
            if not os.path.islink(os.path.join(root, name)):
                total += stat.st_size
                count += 1
    return total, count


def _database_usage(project: str) -> tuple[int, int]:
    db_path = SQLiteStorage.get_project_db_path(project)
    candidates = [
        db_path,
        db_path.with_name(db_path.name + "-wal"),
        db_path.with_name(db_path.name + "-shm"),
        *db_path.parent.glob(f"{db_path.stem}.parquet"),
        *db_path.parent.glob(f"{db_path.stem}_*.parquet"),
    ]
    total = count = 0
    for path in candidates:
        if path.is_file():
            total += path.stat().st_size
            count += 1
    return total, count


def project_usage(project: str) -> dict[str, Any]:
    media_dir = utils.project_media_dir(project)
    files_dir = media_dir / "files"
    usage = {
        "database": _database_usage(project),
        "media": _dir_usage(media_dir, exclude=files_dir),
        "files": _dir_usage(files_dir),
        "artifacts": _dir_usage(utils.project_artifacts_dir(project)),
        "traces": _dir_usage(utils.project_trace_sessions_dir(project)),
    }
    result: dict[str, Any] = {"project": project}
    for category, (size, count) in usage.items():
        result[category] = {"bytes": size, "files": count}
    result["total"] = sum(size for size, _ in usage.values())
    return result


def storage_usage() -> dict[str, Any]:
    """Per-project usage under TRACKIO_DIR, largest first, plus free disk space."""
    projects = [project_usage(p) for p in SQLiteStorage.get_projects()]
    projects.sort(key=lambda p: p["total"], reverse=True)
    root = Path(utils.TRACKIO_DIR)
    disk = None
    try:
        du = shutil.disk_usage(root if root.exists() else root.parent)
        disk = {"total": du.total, "used": du.used, "free": du.free}
    except OSError:
        pass
    return {
        "trackio_dir": str(root),
        "projects": projects,
        "total": sum(p["total"] for p in projects),
        "disk": disk,
    }
