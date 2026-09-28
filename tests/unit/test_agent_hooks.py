import json
import sys

import pytest

from trackio import agent_hooks, cli


def _read(path):
    return json.loads(path.read_text())


def _commands(settings, event):
    return [
        handler["command"]
        for group in settings.get("hooks", {}).get(event, [])
        for handler in group.get("hooks", [])
    ]


def test_install_claude_merges_into_existing_settings(tmp_path):
    settings_file = tmp_path / ".claude" / "settings.local.json"
    settings_file.parent.mkdir()
    settings_file.write_text(
        json.dumps(
            {
                "permissions": {"allow": ["Bash(npm test)"]},
                "hooks": {
                    "Stop": [{"hooks": [{"type": "command", "command": "say done"}]}]
                },
            }
        )
    )
    path, _, changed = agent_hooks.install(
        "claude", root=tmp_path, project="reviews", executable="/opt/bin/trackio"
    )
    assert path == settings_file and changed
    settings = _read(settings_file)
    assert settings["permissions"] == {"allow": ["Bash(npm test)"]}
    assert _commands(settings, "Stop") == [
        "say done",
        "/opt/bin/trackio import agent-session --hook --project reviews",
    ]
    assert _commands(settings, "SessionEnd") == [
        "/opt/bin/trackio import agent-session --hook --project reviews --all"
    ]
    stop_handler = settings["hooks"]["Stop"][1]["hooks"][0]
    assert "async" not in stop_handler


def test_install_is_idempotent_and_updates_in_place(tmp_path):
    agent_hooks.install("claude", root=tmp_path, executable="/opt/bin/trackio")
    _, _, changed = agent_hooks.install(
        "claude", root=tmp_path, executable="/opt/bin/trackio"
    )
    assert not changed
    agent_hooks.install(
        "claude", root=tmp_path, project="p2", executable="/opt/bin/trackio"
    )
    settings = _read(tmp_path / ".claude" / "settings.local.json")
    assert _commands(settings, "Stop") == [
        "/opt/bin/trackio import agent-session --hook --project p2"
    ]


def test_uninstall_removes_only_trackio_hooks(tmp_path):
    settings_file = tmp_path / ".claude" / "settings.local.json"
    settings_file.parent.mkdir()
    settings_file.write_text(
        json.dumps(
            {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "x"}]}]}}
        )
    )
    agent_hooks.install("claude", root=tmp_path, executable="trackio")
    _, changed = agent_hooks.uninstall("claude", root=tmp_path)
    assert changed
    assert _read(settings_file) == {
        "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "x"}]}]}
    }
    _, changed = agent_hooks.uninstall("claude", root=tmp_path)
    assert not changed


def test_uninstall_drops_empty_hooks_section(tmp_path):
    agent_hooks.install("codex", root=tmp_path, executable="trackio")
    agent_hooks.uninstall("codex", root=tmp_path)
    assert _read(tmp_path / ".codex" / "hooks.json") == {}


def test_codex_gets_stop_only_and_quoted_paths(tmp_path):
    agent_hooks.install(
        "codex", root=tmp_path, project="my proj", executable="/opt/my tools/trackio"
    )
    settings = _read(tmp_path / ".codex" / "hooks.json")
    assert list(settings["hooks"]) == ["Stop"]
    assert _commands(settings, "Stop") == [
        "'/opt/my tools/trackio' import agent-session --hook --project 'my proj'"
    ]


def test_global_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    path, _, _ = agent_hooks.install(
        "claude", root=tmp_path / "repo", global_=True, executable="trackio"
    )
    assert path == tmp_path / ".claude" / "settings.json"
    path, _, _ = agent_hooks.install(
        "codex", root=tmp_path / "repo", global_=True, executable="trackio"
    )
    assert path == tmp_path / ".codex" / "hooks.json"


def test_dry_run_and_invalid_json(tmp_path):
    _, settings, changed = agent_hooks.install(
        "claude", root=tmp_path, executable="trackio", dry_run=True
    )
    assert changed and "Stop" in settings["hooks"]
    assert not (tmp_path / ".claude").exists()

    bad = tmp_path / ".codex" / "hooks.json"
    bad.parent.mkdir()
    bad.write_text("{oops")
    with pytest.raises(agent_hooks.HookInstallError):
        agent_hooks.install("codex", root=tmp_path, executable="trackio")
    assert bad.read_text() == "{oops"


def test_cli_install_and_uninstall(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        sys,
        "argv",
        ["trackio", "hooks", "install", "--claude", "--codex", "--dir", str(tmp_path)],
    )
    cli.main()
    out = capsys.readouterr().out
    assert "Installed Claude Code hooks" in out and "Installed Codex hooks" in out
    assert f"project '{tmp_path.name}'" in out
    assert (tmp_path / ".claude" / "settings.local.json").exists()

    monkeypatch.setattr(
        sys,
        "argv",
        ["trackio", "hooks", "uninstall", "--claude", "--dir", str(tmp_path)],
    )
    cli.main()
    assert "Removed Claude Code hooks" in capsys.readouterr().out
    assert _read(tmp_path / ".claude" / "settings.local.json") == {}
