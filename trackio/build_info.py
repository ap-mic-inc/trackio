"""Identifies the exact source revision a Trackio process is running."""

import functools
import hashlib
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _git(*args: str) -> bytes | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(_REPO_ROOT), *args],
            capture_output=True,
            timeout=5,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout


@functools.cache
def git_revision() -> str | None:
    """Short commit hash of the source checkout, e.g. ``9945ca9``.

    Uncommitted changes (edits to tracked files and new untracked files)
    append a hash of those changes (``9945ca9+3f2a1c``), so every distinct
    working tree gets a distinct revision. Returns None for installs that are not a git checkout.
    Computed once per process, so a running server reports the code it
    was started with.
    """
    if not (_REPO_ROOT / ".git").exists():
        return None
    head = _git("rev-parse", "--short", "HEAD")
    if not head:
        return None
    revision = head.decode().strip()
    digest = hashlib.sha256()
    dirty = False
    diff = _git("diff", "HEAD")
    if diff:
        digest.update(diff)
        dirty = True
    untracked = _git("ls-files", "--others", "--exclude-standard", "-z")
    for name in sorted(filter(None, (untracked or b"").split(b"\0"))):
        digest.update(name + b"\0")
        try:
            digest.update((_REPO_ROOT / name.decode()).read_bytes())
        except OSError:
            pass
        dirty = True
    if dirty:
        revision += "+" + digest.hexdigest()[:6]
    return revision


def version_string(version: str) -> str:
    revision = git_revision()
    return f"{version} ({revision})" if revision else version
