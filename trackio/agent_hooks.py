"""Install the hooks that import Claude Code and Codex sessions as traces.

``trackio hooks install`` merges Trackio's hook handlers into the agent's own
settings file and leaves everything else in it untouched. Handlers are
recognised by their ``import agent-session`` command, so re-installing updates
them in place and ``uninstall`` removes only them.

The Stop hook runs synchronously (about a second per turn): headless runs such
as ``claude -p`` exit as soon as the reply is printed, which kills background
(``async``) hooks and skips ``SessionEnd`` before anything is imported.
"""

from __future__ import annotations

import json
import shlex
import shutil
import sys
from pathlib import Path
from typing import Any

IMPORT_COMMAND = "import agent-session --hook"
AGENTS = ("claude", "codex")


class HookInstallError(RuntimeError):
    pass


def trackio_executable() -> str:
    candidate = Path(sys.executable).parent / "trackio"
    if candidate.is_file():
        return str(candidate)
    found = shutil.which("trackio")
    return found or "trackio"


def settings_path(agent: str, root: Path, global_: bool) -> Path:
    if agent == "claude":
        if global_:
            return Path("~/.claude/settings.json").expanduser()
        return root / ".claude" / "settings.local.json"
    if agent == "codex":
        if global_:
            return Path("~/.codex/hooks.json").expanduser()
        return root / ".codex" / "hooks.json"
    raise HookInstallError(f"Unknown agent: {agent}")


def hook_handlers(
    agent: str, executable: str, project: str | None
) -> dict[str, dict[str, Any]]:
    base = f"{shlex.quote(executable)} {IMPORT_COMMAND}"
    if project:
        base += f" --project {shlex.quote(project)}"
    handlers = {"Stop": {"type": "command", "command": base, "timeout": 30}}
    if agent == "claude":
        handlers["SessionEnd"] = {
            "type": "command",
            "command": f"{base} --all",
            "timeout": 60,
        }
    return handlers


def _is_trackio_handler(handler: Any) -> bool:
    return isinstance(handler, dict) and IMPORT_COMMAND in str(
        handler.get("command", "")
    )


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise HookInstallError(
            f"{path} is not valid JSON ({exc}); fix it or install the hooks by hand."
        ) from exc
    if not isinstance(data, dict):
        raise HookInstallError(f"{path} must contain a JSON object.")
    return data


def _without_trackio_handlers(groups: Any) -> list[dict[str, Any]]:
    kept = []
    for group in groups if isinstance(groups, list) else []:
        if not isinstance(group, dict):
            kept.append(group)
            continue
        handlers = [h for h in group.get("hooks", []) if not _is_trackio_handler(h)]
        if handlers:
            kept.append({**group, "hooks": handlers})
        elif not group.get("hooks"):
            kept.append(group)
    return kept


def merged_settings(
    data: dict[str, Any], handlers: dict[str, dict[str, Any]] | None
) -> dict[str, Any]:
    """Return ``data`` with Trackio's handlers replaced by ``handlers``.

    Passing ``None`` removes Trackio's handlers without adding any.
    """
    data = json.loads(json.dumps(data))
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        hooks = {}
    for event in list(hooks):
        remaining = _without_trackio_handlers(hooks[event])
        if remaining:
            hooks[event] = remaining
        else:
            del hooks[event]
    for event, handler in (handlers or {}).items():
        hooks.setdefault(event, []).append({"hooks": [handler]})
    if hooks:
        data["hooks"] = hooks
    else:
        data.pop("hooks", None)
    return data


def install(
    agent: str,
    *,
    root: Path,
    global_: bool = False,
    project: str | None = None,
    executable: str | None = None,
    dry_run: bool = False,
) -> tuple[Path, dict[str, Any], bool]:
    """Install or update the hooks. Returns (path, new settings, changed)."""
    path = settings_path(agent, root, global_)
    current = _load(path)
    handlers = hook_handlers(agent, executable or trackio_executable(), project)
    updated = merged_settings(current, handlers)
    changed = updated != current
    if changed and not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(updated, indent=2) + "\n", encoding="utf-8")
    return path, updated, changed


def uninstall(
    agent: str, *, root: Path, global_: bool = False, dry_run: bool = False
) -> tuple[Path, bool]:
    """Remove Trackio's hooks. Returns (path, changed)."""
    path = settings_path(agent, root, global_)
    if not path.exists():
        return path, False
    current = _load(path)
    updated = merged_settings(current, None)
    changed = updated != current
    if changed and not dry_run:
        path.write_text(json.dumps(updated, indent=2) + "\n", encoding="utf-8")
    return path, changed
