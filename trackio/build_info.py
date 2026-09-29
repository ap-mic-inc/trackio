"""Identifies the exact source revision a Trackio process is running."""

import functools
import hashlib
import json
import subprocess
from importlib import metadata
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


def _installed_revision() -> str | None:
    try:
        text = metadata.distribution("trackio").read_text("direct_url.json")
        commit = json.loads(text or "{}").get("vcs_info", {}).get("commit_id")
    except (metadata.PackageNotFoundError, ValueError, AttributeError, OSError):
        return None
    return commit[:7] if isinstance(commit, str) and commit else None


@functools.cache
def git_revision() -> str | None:
    """Short commit hash of the source checkout, e.g. ``9945ca9``.

    Uncommitted changes (edits to tracked files and new untracked files)
    append a hash of those changes (``9945ca9+3f2a1c``), so every distinct
    working tree gets a distinct revision. Installs made with
    ``pip install "trackio @ git+https://...@<branch>"`` have no checkout;
    for those the commit recorded by the installer (PEP 610
    ``direct_url.json``) is used. Returns None for other installs.
    Computed once per process, so a running server reports the code it
    was started with.
    """
    if not (_REPO_ROOT / ".git").exists():
        return _installed_revision()
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
