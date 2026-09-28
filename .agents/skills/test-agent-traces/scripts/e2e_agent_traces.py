"""End-to-end test of coding-agent trace collection with real Claude Code and Codex.

Starts an isolated Trackio server, installs the hooks with `trackio hooks install`,
drives real `claude -p` / `codex exec` turns in scratch repositories, and checks
what the hooks imported. Nothing outside the work directory is modified: Claude
Code hooks go to the scratch repo's .claude/settings.local.json, and Codex runs
with a scratch CODEX_HOME holding a copy of your auth.json (deleted at the end).

    .venv/bin/python .agents/skills/test-agent-traces/scripts/e2e_agent_traces.py \\
        [--agents claude,codex] [--port 7863] [--keep] [--codex-no-sandbox]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

TRACKIO = Path(sys.executable).parent / "trackio"
RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(ok), detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))


def run(cmd: list[str], env: dict, cwd: Path, timeout: int = 400) -> str:
    result = subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    output = (result.stdout + result.stderr).strip()
    print(f"  $ {' '.join(cmd[:3])} …  → exit {result.returncode}: {output[-160:]!r}")
    return output


def start_server(work: Path, port: int, token: str) -> subprocess.Popen:
    env = {
        **os.environ,
        "TRACKIO_DIR": str(work / "server"),
        "TRACKIO_WRITE_TOKEN": token,
        "GRADIO_SERVER_PORT": str(port),
    }
    log = open(work / "server.log", "w")
    proc = subprocess.Popen(
        [str(TRACKIO), "show"], env=env, stdout=log, stderr=subprocess.STDOUT
    )
    for _ in range(60):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/version", timeout=2)
            return proc
        except OSError:
            time.sleep(1)
    proc.kill()
    raise SystemExit(f"Server did not start on port {port}; see {work / 'server.log'}")


def query(work: Path, project: str) -> list[dict]:
    code = f"""
import json
from trackio.sqlite_storage import SQLiteStorage as S
out = []
configs = S.get_all_run_configs({project!r})
for run in S.get_run_records({project!r}):
    traces = sorted(S.get_traces({project!r}, run_id=run["id"]), key=lambda t: t["step"])
    out.append({{"name": run["name"], "group": configs.get(run["id"], {{}}).get("_Group"),
                 "traces": [{{"step": t["step"], "messages": t["messages"], "spans": t["spans"]}} for t in traces]}})
print(json.dumps(out))
"""
    env = {**os.environ, "TRACKIO_DIR": str(work / "server")}
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def claude_scenario(work: Path, env: dict) -> None:
    print("\n[Claude Code]")
    if not shutil.which("claude"):
        check("claude CLI available", False, "claude not on PATH")
        return
    repo = work / "claude-repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / "data.txt").write_text("a\nb\nc\n")
    (repo / "app.py").write_text("print('hi')\n")
    run(
        [str(TRACKIO), "hooks", "install", "--claude", "--project", "e2e-claude"],
        env,
        repo,
    )
    run(
        [
            "claude",
            "-p",
            "Run 'wc -l data.txt' and then 'cat missing-file.txt' (it will "
            "fail). Reply in one sentence with the line count.",
            "--allowedTools",
            "Bash",
        ],
        env,
        repo,
    )
    run(
        [
            "claude",
            "-p",
            "--continue",
            "Use the Task tool (a subagent) to read app.py and "
            "report what it prints. Reply with just the subagent's answer.",
            "--allowedTools",
            "Bash",
            "Read",
            "Task",
            "Agent",
        ],
        env,
        repo,
    )
    run(["claude", "-p", "--continue", "Reply with just: third turn"], env, repo)

    runs = query(work, "e2e-claude")
    check("one Claude run imported", len(runs) == 1, f"{len(runs)} runs")
    if not runs:
        return
    traces = runs[0]["traces"]
    check(
        "group is claude-code", runs[0]["group"] == "claude-code", str(runs[0]["group"])
    )
    check(
        "three turns imported",
        [t["step"] for t in traces] == [1, 2, 3],
        str([t["step"] for t in traces]),
    )
    if len(traces) < 3:
        return
    first, second, third = traces
    tool_status = [s.get("status") for s in first["spans"] if s.get("kind") == "tool"]
    check("failed tool call marked error", "error" in tool_status, str(tool_status))
    check(
        "successful tool call marked success",
        "success" in tool_status,
        str(tool_status),
    )
    spans = {s["id"]: s for s in second["spans"]}
    agent = [
        s
        for s in second["spans"]
        if s.get("kind") == "tool" and s["name"] in {"Agent", "Task"}
    ]
    nested = [
        s for s in second["spans"] if agent and s.get("parent_id") == agent[0]["id"]
    ]
    check("subagent call recorded", bool(agent))
    check("subagent work nested under it", bool(nested), f"{len(nested)} child spans")
    check(
        "final reply captured",
        third["messages"][-1]["role"] == "assistant"
        and "third turn" in third["messages"][-1]["content"].lower(),
    )
    check(
        "root span has prompt and reply",
        bool(spans.get("turn-2", {}).get("input"))
        and bool(spans.get("turn-2", {}).get("output")),
    )


def codex_scenario(work: Path, env: dict, no_sandbox: bool) -> None:
    print("\n[Codex]")
    if not shutil.which("codex"):
        check("codex CLI available", False, "codex not on PATH")
        return
    source_home = Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser()
    if not (source_home / "auth.json").is_file():
        check("codex is logged in", False, f"no {source_home}/auth.json")
        return
    repo = work / "codex-repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / "notes.txt").write_text("x\ny\n")
    home = work / "codex-home"
    home.mkdir()
    old_umask = os.umask(0o077)
    try:
        shutil.copy2(source_home / "auth.json", home / "auth.json")
    finally:
        os.umask(old_umask)
    config = (
        (source_home / "config.toml").read_text()
        if (source_home / "config.toml").is_file()
        else ""
    )
    (home / "config.toml").write_text(
        f'{config}\n[projects."{repo}"]\ntrust_level = "trusted"\n'
    )
    codex_env = {**env, "CODEX_HOME": str(home)}
    run(
        [
            str(TRACKIO),
            "hooks",
            "install",
            "--codex",
            "--global",
            "--project",
            "e2e-codex",
        ],
        codex_env,
        repo,
    )
    check("hook written to CODEX_HOME", (home / "hooks.json").is_file())
    base = ["codex", "exec", "--dangerously-bypass-hook-trust", "--skip-git-repo-check"]
    sandbox = (
        ["--dangerously-bypass-approvals-and-sandbox"]
        if no_sandbox
        else ["-s", "workspace-write"]
    )
    run(
        [
            *base,
            *sandbox,
            "Run 'wc -l notes.txt' and then 'cat missing.txt' (expected to "
            "fail). Answer in one sentence with the line count.",
        ],
        codex_env,
        repo,
    )
    run([*base, "resume", "--last", "Reply with just: second turn"], codex_env, repo)

    runs = query(work, "e2e-codex")
    check("one Codex run imported", len(runs) == 1, f"{len(runs)} runs")
    if not runs:
        return
    traces = runs[0]["traces"]
    check("group is codex", runs[0]["group"] == "codex", str(runs[0]["group"]))
    check(
        "two turns imported",
        [t["step"] for t in traces] == [1, 2],
        str([t["step"] for t in traces]),
    )
    if not traces:
        return
    tools = [s for s in traces[0]["spans"] if s.get("kind") == "tool"]
    gens = [s for s in traces[0]["spans"] if s.get("kind") == "generation"]
    check("tool call recorded", bool(tools), f"{len(tools)} tool spans")
    check(
        "failing command marked error",
        any(s.get("status") == "error" for s in tools),
        str([s.get("status") for s in tools]),
    )
    check("model calls carry token usage", gens and all(s.get("usage") for s in gens))
    check(
        "second turn reply captured",
        len(traces) > 1
        and "second turn" in traces[-1]["messages"][-1]["content"].lower(),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--agents", default="claude,codex")
    parser.add_argument("--port", type=int, default=7863)
    parser.add_argument(
        "--keep", action="store_true", help="Leave the server and work dir"
    )
    parser.add_argument(
        "--codex-no-sandbox",
        action="store_true",
        help="Run Codex without its sandbox (for containers where it cannot start)",
    )
    args = parser.parse_args()
    if not TRACKIO.is_file():
        raise SystemExit(f"Run with the repo virtualenv's python; {TRACKIO} not found")

    work = Path(tempfile.mkdtemp(prefix="trackio-agent-e2e-"))
    token = secrets.token_urlsafe(16)
    print(
        f"work dir: {work}\nserver:   http://127.0.0.1:{args.port}?write_token={token}"
    )
    server = start_server(work, args.port, token)
    env = {
        **os.environ,
        "TRACKIO_SERVER_URL": f"http://127.0.0.1:{args.port}",
        "TRACKIO_WRITE_TOKEN": token,
        "TRACKIO_DIR": str(work / "client-fallback"),
    }
    try:
        agents = {a.strip() for a in args.agents.split(",")}
        if "claude" in agents:
            claude_scenario(work, env)
        if "codex" in agents:
            codex_scenario(work, env, args.codex_no_sandbox)
        fallback = work / "client-fallback"
        check(
            "nothing fell back to local storage",
            not fallback.exists() or not any(fallback.iterdir()),
        )
    finally:
        auth_copy = work / "codex-home" / "auth.json"
        if auth_copy.exists():
            auth_copy.unlink()
        claude_sessions = Path("~/.claude/projects").expanduser() / re.sub(
            r"[^A-Za-z0-9]", "-", str(work / "claude-repo")
        )
        if not args.keep and claude_sessions.is_dir():
            shutil.rmtree(claude_sessions)
        if args.keep:
            print(f"\nServer left running (pid {server.pid}); work dir kept: {work}")
        else:
            server.terminate()
            server.wait(timeout=20)
            shutil.rmtree(work, ignore_errors=True)

    failed = [name for name, ok, _ in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
