import io
import json
import sys

import pytest

from trackio import agent_import, cli
from trackio.sqlite_storage import SQLiteStorage


def _write_jsonl(path, records):
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    return path


def _claude_records(session_id="11111111-aaaa-bbbb-cccc-000000000001"):
    def rec(ts, message, **extra):
        return {
            "type": message["role"],
            "sessionId": session_id,
            "cwd": "/work/my-repo",
            "timestamp": ts,
            "message": message,
            **extra,
        }

    usage = {
        "input_tokens": 10,
        "cache_read_input_tokens": 100,
        "cache_creation_input_tokens": 5,
        "output_tokens": 7,
    }
    return [
        {"type": "ai-title", "aiTitle": "Fix the loader", "sessionId": session_id},
        rec(
            "2026-09-28T10:00:00Z",
            {"role": "user", "content": "Caveat: local commands below"},
            isMeta=True,
        ),
        rec(
            "2026-09-28T10:00:01Z",
            {"role": "user", "content": "<command-name>/clear</command-name>"},
        ),
        rec(
            "2026-09-28T10:00:02Z",
            {"role": "user", "content": "Review item 1"},
        ),
        rec(
            "2026-09-28T10:00:04Z",
            {
                "role": "assistant",
                "id": "msg_a",
                "model": "claude-test",
                "usage": usage,
                "content": [
                    {"type": "text", "text": "Checking."},
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "Bash",
                        "input": {"command": "grep x"},
                    },
                ],
            },
        ),
        rec(
            "2026-09-28T10:00:04Z",
            {
                "role": "assistant",
                "id": "msg_a",
                "model": "claude-test",
                "usage": usage,
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_2",
                        "name": "Task",
                        "input": {"prompt": "look deeper"},
                    }
                ],
            },
        ),
        rec(
            "2026-09-28T10:00:05Z",
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_1",
                        "content": "exit 1",
                        "is_error": True,
                    }
                ],
            },
        ),
        rec(
            "2026-09-28T10:00:06Z",
            {"role": "user", "content": "look deeper"},
            isSidechain=True,
        ),
        rec(
            "2026-09-28T10:00:07Z",
            {
                "role": "assistant",
                "id": "msg_sub",
                "model": "claude-test",
                "usage": {"input_tokens": 3, "output_tokens": 2},
                "content": [{"type": "text", "text": "sub result"}],
            },
            isSidechain=True,
        ),
        rec(
            "2026-09-28T10:00:08Z",
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_2",
                        "content": "done",
                    }
                ],
            },
        ),
        rec(
            "2026-09-28T10:00:10Z",
            {
                "role": "assistant",
                "id": "msg_b",
                "model": "claude-test",
                "usage": {"input_tokens": 20, "output_tokens": 4},
                "content": [
                    {
                        "type": "text",
                        "text": "Item 1 passes. api_key=sk-abcdefghijklmnopqrstuvwxyz0123",
                    }
                ],
            },
        ),
        rec(
            "2026-09-28T10:01:00Z",
            {"role": "user", "content": "Review item 2"},
        ),
    ]


def _codex_records():
    def item(ts, payload):
        return {"timestamp": ts, "type": "response_item", "payload": payload}

    def event(ts, payload):
        return {"timestamp": ts, "type": "event_msg", "payload": payload}

    return [
        {
            "timestamp": "2026-09-28T09:00:00Z",
            "type": "session_meta",
            "payload": {"id": "22222222-cccc-dddd-eeee-000000000002", "cwd": "/w/r"},
        },
        {
            "timestamp": "2026-09-28T09:00:00Z",
            "type": "turn_context",
            "payload": {"model": "gpt-test"},
        },
        event("2026-09-28T09:00:01Z", {"type": "task_started", "turn_id": "t1"}),
        item(
            "2026-09-28T09:00:01Z",
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "<environment_context>x"}],
            },
        ),
        item(
            "2026-09-28T09:00:01Z",
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "List files"}],
            },
        ),
        item("2026-09-28T09:00:05Z", {"type": "reasoning", "summary": []}),
        item(
            "2026-09-28T09:00:05Z",
            {
                "type": "function_call",
                "name": "exec",
                "call_id": "c1",
                "arguments": '{"cmd": "ls"}',
            },
        ),
        {
            "timestamp": "2026-09-28T09:00:05Z",
            "type": "token_usage_record",
            "payload": {
                "response_id": "resp_1",
                "usage": {
                    "input_tokens": 50,
                    "cached_input_tokens": 40,
                    "output_tokens": 6,
                },
            },
        },
        item(
            "2026-09-28T09:00:06Z",
            {"type": "function_call_output", "call_id": "c1", "output": "a.py"},
        ),
        item(
            "2026-09-28T09:00:09Z",
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "One file: a.py"}],
            },
        ),
        {
            "timestamp": "2026-09-28T09:00:09Z",
            "type": "token_usage_record",
            "payload": {
                "response_id": "resp_2",
                "usage": {"input_tokens": 60, "output_tokens": 5},
            },
        },
        event(
            "2026-09-28T09:00:09Z",
            {"type": "task_complete", "turn_id": "t1", "duration_ms": 8000},
        ),
    ]


def test_claude_turns_skip_meta_and_wrappers(tmp_path):
    session = agent_import.load_session(
        _write_jsonl(tmp_path / "c.jsonl", _claude_records())
    )
    assert session["provider"] == "Claude Code"
    assert session["title"] == "Fix the loader"
    assert [t.prompt for t in session["turns"]] == ["Review item 1", "Review item 2"]


def test_claude_turn_spans_usage_and_errors(tmp_path):
    session = agent_import.load_session(
        _write_jsonl(tmp_path / "c.jsonl", _claude_records())
    )
    turn = session["turns"][0]
    metrics = turn.metrics()
    assert metrics["agent/tool_calls"] == 2
    assert metrics["agent/tool_errors"] == 1
    assert metrics["agent/model_calls"] == 3
    assert metrics["agent/input_tokens"] == 115 + 3 + 20
    assert metrics["agent/cached_input_tokens"] == 100
    assert metrics["agent/duration_s"] == 8.0

    spans = {s["id"]: s for s in turn.spans()}
    root = spans["turn-1"]
    assert root["input"] == "Review item 1"
    assert root["output"].startswith("Checking.")
    assert spans["tool-toolu_1"]["status"] == "error"
    assert spans["tool-toolu_1"]["parent_id"] == "gen-msg_a"
    assert spans["gen-msg_sub"]["parent_id"] == "tool-toolu_2"
    assert [m["role"] for m in turn.messages] == ["user", "assistant"]
    assert "sub result" not in turn.messages[-1]["content"]


def test_codex_turns_generation_timing_and_parenting(tmp_path):
    session = agent_import.load_session(
        _write_jsonl(tmp_path / "x.jsonl", _codex_records())
    )
    assert session["provider"] == "Codex"
    assert session["model"] == "gpt-test"
    [turn] = session["turns"]
    assert turn.prompt == "List files"
    assert turn.turn_id == "t1"
    spans = {s["id"]: s for s in turn.spans()}
    first = spans["gen-resp_1"]
    assert first["start_time"] == "2026-09-28T09:00:01Z"
    assert spans["tool-c1"]["parent_id"] == "gen-resp_1"
    assert spans["tool-c1"]["input"] == {"cmd": "ls"}
    assert spans["gen-resp_2"]["start_time"] == "2026-09-28T09:00:06Z"
    assert turn.metrics()["agent/duration_s"] == 8.0
    assert turn.messages[-1] == {"role": "assistant", "content": "One file: a.py"}


def test_import_is_idempotent_and_updates_growing_sessions(temp_dir, tmp_path):
    records = _claude_records()
    path = _write_jsonl(tmp_path / "c.jsonl", records[:-1])
    session = agent_import.load_session(path)
    agent_import.write_entries(
        agent_import.build_log_entries(session, project="agents")
    )
    agent_import.write_entries(
        agent_import.build_log_entries(session, project="agents")
    )

    _write_jsonl(
        path,
        records
        + [
            {
                "type": "assistant",
                "sessionId": records[1]["sessionId"],
                "timestamp": "2026-09-28T10:01:05Z",
                "message": {
                    "role": "assistant",
                    "id": "msg_c",
                    "content": [{"type": "text", "text": "Item 2 fails."}],
                },
            }
        ],
    )
    session = agent_import.load_session(path)
    agent_import.write_entries(
        agent_import.build_log_entries(session, project="agents", last=1)
    )

    run_id, run_name = agent_import.run_identity(session)
    [record] = SQLiteStorage.get_run_records("agents")
    assert record["id"] == run_id and record["name"] == run_name
    traces = SQLiteStorage.get_traces("agents", run_id=run_id)
    assert sorted(t["step"] for t in traces) == [1, 2]
    second = next(t for t in traces if t["step"] == 2)
    assert second["messages"][-1]["content"] == "Item 2 fails."
    config = SQLiteStorage.get_all_run_configs("agents")[run_id]
    assert config["_Group"] == "claude-code"
    assert config["title"] == "Fix the loader"


def test_secrets_are_scrubbed(tmp_path):
    session = agent_import.load_session(
        _write_jsonl(tmp_path / "c.jsonl", _claude_records())
    )
    [entry, _] = agent_import.build_log_entries(session, project="p")
    text = json.dumps(entry["metrics"]["trace"])
    assert "sk-abcdefghijklmnopqrstuvwxyz0123" not in text
    [entry, _] = agent_import.build_log_entries(session, project="p", scrub=False)
    assert "sk-abcdefghijklmnopqrstuvwxyz0123" in json.dumps(entry["metrics"]["trace"])


def test_distinct_log_ids_per_turn(tmp_path):
    session = agent_import.load_session(
        _write_jsonl(tmp_path / "c.jsonl", _claude_records())
    )
    first, second = agent_import.build_log_entries(session, project="p")
    assert first["log_id"][:7] != second["log_id"][:7]
    assert first["config"] is not None and second["config"] is None


def test_apply_final_reply_fills_missing_answer(tmp_path):
    session = agent_import.load_session(
        _write_jsonl(tmp_path / "c.jsonl", _claude_records())
    )
    agent_import.apply_final_reply(session, "Item 2 passes.")
    assert session["turns"][-1].messages[-1]["content"] == "Item 2 passes."
    agent_import.apply_final_reply(session, "ignored")
    assert session["turns"][-1].messages[-1]["content"] == "Item 2 passes."


def test_unsupported_format(tmp_path):
    path = _write_jsonl(tmp_path / "g.jsonl", [{"hello": "world"}])
    with pytest.raises(agent_import.AgentSessionError):
        agent_import.load_session(path)


def _run_cli(monkeypatch, argv, stdin=""):
    monkeypatch.setattr(sys, "argv", ["trackio", *argv])
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
    cli.main()


def test_cli_hook_imports_last_turns_into_cwd_project(temp_dir, tmp_path, monkeypatch):
    path = _write_jsonl(tmp_path / "c.jsonl", _claude_records())
    payload = {
        "session_id": "x",
        "transcript_path": str(path),
        "cwd": "/work/review-repo",
        "hook_event_name": "Stop",
        "last_assistant_message": "Item 2 passes.",
    }
    _run_cli(
        monkeypatch,
        ["import", "agent-session", "--hook", "--last", "1"],
        json.dumps(payload),
    )
    session = agent_import.load_session(path)
    run_id, _ = agent_import.run_identity(session)
    traces = SQLiteStorage.get_traces("review-repo", run_id=run_id)
    assert [t["step"] for t in traces] == [2]
    assert traces[0]["messages"][-1]["content"] == "Item 2 passes."


def test_cli_hook_never_fails(temp_dir, monkeypatch, capsys):
    _run_cli(monkeypatch, ["import", "agent-session", "--hook"], "{}")
    assert "transcript_path" in capsys.readouterr().err
    _run_cli(
        monkeypatch,
        ["import", "agent-session", "--hook"],
        json.dumps({"transcript_path": "/does/not/exist.jsonl"}),
    )
    assert "not found" in capsys.readouterr().err


def test_bulk_log_replace_overwrites_same_log_id(temp_dir):
    SQLiteStorage.bulk_log(
        "p", "r", [{"x": 1}], steps=[1], log_ids=["same"], run_id="rid"
    )
    SQLiteStorage.bulk_log(
        "p", "r", [{"x": 2}], steps=[1], log_ids=["same"], run_id="rid"
    )
    assert SQLiteStorage.get_logs("p", "r", run_id="rid")[0]["x"] == 1
    SQLiteStorage.bulk_log(
        "p", "r", [{"x": 3}], steps=[1], log_ids=["same"], run_id="rid", replace=True
    )
    logs = SQLiteStorage.get_logs("p", "r", run_id="rid")
    assert [log["x"] for log in logs] == [3]


def test_claude_subagent_files_nest_under_agent_call(tmp_path):
    session_id = "33333333-aaaa-bbbb-cccc-000000000003"

    def rec(ts, message, **extra):
        return {"sessionId": session_id, "timestamp": ts, "message": message, **extra}

    main = _write_jsonl(
        tmp_path / f"{session_id}.jsonl",
        [
            rec("2026-09-28T10:00:00Z", {"role": "user", "content": "Delegate it"}),
            rec(
                "2026-09-28T10:00:01Z",
                {
                    "role": "assistant",
                    "id": "msg_main",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_agent",
                            "name": "Agent",
                            "input": {"prompt": "read app.py"},
                        }
                    ],
                },
            ),
            rec(
                "2026-09-28T10:00:09Z",
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_agent",
                            "content": "prints hi",
                        }
                    ],
                },
            ),
        ],
    )
    subagents = tmp_path / session_id / "subagents"
    subagents.mkdir(parents=True)
    (subagents / "agent-abc.meta.json").write_text(
        json.dumps({"toolUseId": "toolu_agent", "spawnDepth": 1})
    )
    _write_jsonl(
        subagents / "agent-abc.jsonl",
        [
            rec(
                "2026-09-28T10:00:02Z",
                {"role": "user", "content": "read app.py"},
                isSidechain=True,
            ),
            rec(
                "2026-09-28T10:00:04Z",
                {
                    "role": "assistant",
                    "id": "msg_sub",
                    "usage": {"input_tokens": 9, "output_tokens": 1},
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_read",
                            "name": "Read",
                            "input": {"file_path": "app.py"},
                        }
                    ],
                },
                isSidechain=True,
            ),
            rec(
                "2026-09-28T10:00:05Z",
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_read",
                            "content": "print('hi')",
                        }
                    ],
                },
                isSidechain=True,
            ),
        ],
    )
    [turn] = agent_import.load_session(main)["turns"]
    spans = {s["id"]: s for s in turn.spans()}
    sub_generation = spans["gen-agent-abc-msg_sub"]
    assert sub_generation["parent_id"] == "tool-toolu_agent"
    assert sub_generation["start_time"] == "2026-09-28T10:00:02Z"
    assert spans["tool-toolu_read"]["parent_id"] == sub_generation["id"]
    assert spans["tool-toolu_read"]["status"] == "success"
    assert turn.metrics()["agent/tool_calls"] == 2
    assert turn.messages == [{"role": "user", "content": "Delegate it"}]


@pytest.mark.parametrize(
    "output, failed",
    [
        ('Script completed\n{"exit_code":0,"output":"2 notes.txt"}', False),
        ('{"exit_code":0}\n{"exit_code":1,"output":"cat: missing"}', True),
        ('{\\"exit_code\\":1}', True),
        ("Process exited with code 2", True),
        ("Exit code: 0\nok", False),
        ("plain output", None),
    ],
)
def test_codex_tool_failure_from_exit_codes(output, failed):
    assert agent_import._codex_tool_failed(output) is failed

