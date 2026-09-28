---
name: test-agent-traces
description: End-to-end test of Claude Code and Codex session collection (`trackio hooks install`, `trackio import agent-session`) with the real agents. Use after changing agent_import.py, agent_hooks.py, the hook CLI, bulk_log replace mode, or the Traces page, or when asked to 真實測試 / e2e test the Claude or Codex integration.
---

# Test coding-agent trace collection end to end

Unit tests (`tests/unit/test_agent_import.py`, `tests/unit/test_agent_hooks.py`)
use synthetic transcripts. The agents' real transcript formats and hook
behaviour drift between releases, so also run the real flow before shipping.
Every bug below was only found this way.

## Run it

From the repository root, with the repo virtualenv:

```bash
.venv/bin/python .agents/skills/test-agent-traces/scripts/e2e_agent_traces.py \
  [--agents claude,codex] [--port 7863] [--keep] [--codex-no-sandbox]
```

It starts an isolated server with a random write token, installs the hooks with
`trackio hooks install`, drives real turns, queries what was imported, and
prints PASS/FAIL per check (exit code 1 on any failure). It costs a few cents of
model usage.

| Scenario | What it checks |
| --- | --- |
| Claude turn 1: a passing and a failing `Bash` call | tool spans marked `success` / `error` |
| Claude turn 2 (`--continue`): a subagent reads a file | `Agent` span with the subagent's model and tool calls nested under it |
| Claude turn 3 (`--continue`) | three turns in one run, final reply captured |
| Codex turn 1: passing and failing command | tool span, `error` from the exit code, token usage on model calls |
| Codex turn 2 (`exec resume --last`) | second turn in the same run |
| All | hooks sent to `TRACKIO_SERVER_URL`, nothing fell back to local storage |

- `--keep` leaves the server running and prints its URL, so you can open the
  Traces page (and screenshot it with Playwright) before cleaning up.
- `--codex-no-sandbox` runs Codex with
  `--dangerously-bypass-approvals-and-sandbox`. Use it in containers where the
  Codex sandbox cannot start (every command then fails to launch, and the
  "failing command" check passes for the wrong reason). The commands only touch
  the scratch repository.

## Isolation and cleanup

- Claude Code hooks go to the scratch repo's `.claude/settings.local.json`;
  your own settings are not touched. Claude still writes the test sessions to
  `~/.claude/projects/<encoded scratch path>/`; the script deletes that
  directory at the end unless `--keep`.
- Codex runs with a scratch `CODEX_HOME` containing a copy of your `auth.json`
  (mode 600) and `config.toml` plus a trust entry for the scratch repo. The hook
  is installed with `--global`, which also exercises `CODEX_HOME` support. The
  copied `auth.json` is always deleted, even with `--keep`.
- Never point the test at the user's dashboard data or install hooks in their
  real settings to test; use `--dir`/`CODEX_HOME`/scratch repos instead.

## Things the real agents do that synthetic tests missed

- **Headless runs kill background hooks.** `claude -p` exits right after the
  reply, killing `async` hooks and skipping `SessionEnd`, so nothing was
  imported. The Stop hook must stay synchronous. Check with
  `claude -p ... --debug-file /tmp/d.txt` and grep for `Hooks:`.
- **Codex skips untrusted hooks silently.** Nothing is logged; the hook simply
  never runs. Trust it in `/hooks` (interactive) or pass
  `--dangerously-bypass-hook-trust` to `codex exec`. Trust is tied to the hook's
  exact command, so reinstalling with other options needs a new trust.
- **Claude Code subagents live in separate files**:
  `<session>/subagents/agent-<id>.jsonl` plus `.meta.json` whose `toolUseId`
  names the spawning `Agent` call. The tool is called `Agent` in current
  releases (`Task` in older ones).
- **Codex tool output has no success flag**; failures show up as non-zero
  `exit_code` values inside the output text.
- **Codex session ids are UUIDv7** (time-ordered), so their prefixes collide for
  sessions started in the same minute.
- **The transcript can lag the Stop hook.** The hook payload's
  `last_assistant_message` fills in the final reply.

## When a check fails

1. Rerun with `--keep`, open the printed server URL, and inspect the run on the
   Traces page.
2. Look at the raw transcript: Claude Code in
   `~/.claude/projects/<encoded path>/<session>.jsonl`, Codex in
   `<work>/codex-home/sessions/YYYY/MM/DD/rollout-*.jsonl`. Print record types
   and key names only, not contents, when sharing them.
3. Replay the import by hand against the kept server:
   `TRACKIO_SERVER_URL=... TRACKIO_WRITE_TOKEN=... .venv/bin/trackio import agent-session <file> --project e2e-claude`.
4. Add a synthetic regression test for the format change to
   `tests/unit/test_agent_import.py`, then rerun this script.
