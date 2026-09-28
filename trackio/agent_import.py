"""Import coding-agent sessions (Claude Code, Codex) as Trackio traces.

A session transcript becomes one Trackio run, and every turn (one user prompt
and everything the agent did until it replied) becomes one ``trackio.Trace``
logged at ``step = turn``. Each trace carries the conversation as messages and
the work as spans: one ``generation`` span per model call (model and token
usage) and one ``tool`` span per tool call (input, output, status). Per-turn
counters are logged as ``agent/*`` metrics.

Imports are idempotent: run ids and log ids are derived from the session id,
and entries are written with ``replace=True``, so re-importing a session (for
example from a hook after every turn) updates turns in place instead of
duplicating them.
"""

from __future__ import annotations

import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import huggingface_hub

from trackio import logbook_trace, utils
from trackio.agent_sessions import parse_time, safe_id
from trackio.remote_client import RemoteClient
from trackio.sqlite_storage import SQLiteStorage
from trackio.trace import Trace

MAX_TEXT_CHARS = 8000
TRACE_KEY = "trace"
SUPPORTED_PROVIDERS = {"claude": "Claude Code", "codex": "Codex"}
PROVIDER_SLUGS = {"Claude Code": "claude-code", "Codex": "codex"}
RUN_NAME_PREFIXES = {"Claude Code": "claude", "Codex": "codex"}
_LOG_ID_NAMESPACE = uuid.UUID("5b0f5a0e-7a6f-4c1e-9f55-2a8c0b1d7e41")
_WRAPPER_PREFIXES = (
    "<command-",
    "<local-command",
    "<environment_context",
    "<user_instructions",
    "<user_shell_command",
    "<turn_aborted",
    "<system-reminder",
    "# AGENTS.md instructions",
)


class AgentSessionError(ValueError):
    pass


def _truncate(text: str) -> str:
    if len(text) <= MAX_TEXT_CHARS:
        return text
    omitted = len(text) - MAX_TEXT_CHARS
    return f"{text[:MAX_TEXT_CHARS]}\n… [{omitted} more characters truncated]"


def _clean(value: Any, scrub: bool) -> Any:
    if isinstance(value, str):
        if scrub:
            value, _ = logbook_trace.scrub_text(value)
        return _truncate(value)
    if isinstance(value, list):
        return [_clean(item, scrub) for item in value]
    if isinstance(value, dict):
        return {key: _clean(item, scrub) for key, item in value.items()}
    return value


def _is_wrapper_text(text: str) -> bool:
    return text.lstrip().startswith(_WRAPPER_PREFIXES)


def _later(a: str | None, b: str | None) -> str | None:
    if a is None:
        return b
    if b is None:
        return a
    ta, tb = parse_time(a), parse_time(b)
    if ta is None or tb is None:
        return b
    return b if tb >= ta else a


class _Turn:
    def __init__(self, index: int, started_at: str | None, prompt: str):
        self.index = index
        self.started_at = started_at
        self.ended_at = started_at
        self.last_activity = started_at
        self.prompt = prompt
        self.messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        self.generations: dict[str, dict[str, Any]] = {}
        self.tools: dict[str, dict[str, Any]] = {}
        self.order: list[dict[str, Any]] = []
        self.models: list[str] = []
        self.turn_id: str | None = None
        self.status: str | None = None
        self.duration_ms: int | None = None
        self.response_start: str | None = None
        self.response_tools: list[dict[str, Any]] = []

    def touch(self, ts: str | None) -> None:
        if ts:
            self.ended_at = _later(self.ended_at, ts)
            self.last_activity = ts

    def root_id(self) -> str:
        return f"turn-{self.index}"

    def add_assistant_text(self, text: str, ts: str | None) -> None:
        text = text.strip()
        if not text:
            return
        last = self.messages[-1]
        if last["role"] == "assistant":
            last["content"] = f"{last['content']}\n\n{text}"
        else:
            self.messages.append({"role": "assistant", "content": text})
        self.touch(ts)

    def has_final_reply(self) -> bool:
        return self.messages[-1]["role"] == "assistant"

    def add_generation(
        self,
        gen_id: str,
        model: str | None,
        usage: dict[str, int],
        ts: str | None,
        parent_id: str | None = None,
        start: str | None = None,
    ) -> dict[str, Any]:
        span = self.generations.get(gen_id)
        if span is None:
            span = {
                "id": f"gen-{safe_id(gen_id)}",
                "parent_id": parent_id or self.root_id(),
                "name": model or "model call",
                "kind": "generation",
                "start_time": start or self.last_activity or ts,
                "end_time": ts,
                "status": "success",
            }
            if model:
                span["model"] = model
                if model not in self.models:
                    self.models.append(model)
            self.generations[gen_id] = span
            self.order.append(span)
        if usage:
            span["usage"] = usage
        span["end_time"] = _later(span.get("end_time"), ts)
        self.touch(ts)
        return span

    def start_tool(
        self,
        call_id: str,
        name: str,
        tool_input: Any,
        ts: str | None,
        parent_id: str | None = None,
    ) -> dict[str, Any]:
        span = {
            "id": f"tool-{safe_id(call_id)}",
            "parent_id": parent_id or self.root_id(),
            "name": name,
            "kind": "tool",
            "start_time": ts,
            "input": tool_input,
        }
        self.tools[call_id] = span
        self.order.append(span)
        self.touch(ts)
        return span

    def begin_response(self) -> None:
        if self.response_start is None:
            self.response_start = self.last_activity

    def end_response(
        self, gen_id: str, model: str | None, usage: dict[str, int], ts: str | None
    ) -> None:
        generation = self.add_generation(
            gen_id, model, usage, ts, start=self.response_start
        )
        for tool in self.response_tools:
            tool["parent_id"] = generation["id"]
        self.response_start = None
        self.response_tools = []

    def finish_tool(
        self, call_id: str, output: Any, ts: str | None, is_error: bool | None
    ) -> None:
        span = self.tools.get(call_id)
        if span is None:
            return
        span["output"] = output
        span["end_time"] = ts
        if is_error is not None:
            span["status"] = "error" if is_error else "success"
        self.touch(ts)

    def open_tool_parent(self, names: set[str]) -> str | None:
        for span in reversed(self.order):
            if (
                span["kind"] == "tool"
                and span["name"] in names
                and "end_time" not in span
            ):
                return span["id"]
        return None

    def spans(self) -> list[dict[str, Any]]:
        status = self.status
        if status is None:
            status = "success" if self.has_final_reply() else "incomplete"
        root = {
            "id": self.root_id(),
            "name": f"turn {self.index}",
            "kind": "span",
            "start_time": self.started_at,
            "end_time": self.ended_at,
            "status": status,
            "input": self.prompt,
        }
        if self.has_final_reply():
            root["output"] = self.messages[-1]["content"]
        if self.duration_ms is not None:
            root["duration_ms"] = self.duration_ms
        return [root, *self.order]

    def metrics(self) -> dict[str, float | int]:
        tools = list(self.tools.values())
        input_tokens = sum(
            g.get("usage", {}).get("input_tokens", 0) for g in self.generations.values()
        )
        output_tokens = sum(
            g.get("usage", {}).get("output_tokens", 0)
            for g in self.generations.values()
        )
        cached = sum(
            g.get("usage", {}).get("cached_input_tokens", 0)
            for g in self.generations.values()
        )
        values: dict[str, float | int] = {
            "agent/tool_calls": len(tools),
            "agent/tool_errors": sum(1 for t in tools if t.get("status") == "error"),
            "agent/model_calls": len(self.generations),
            "agent/input_tokens": input_tokens,
            "agent/output_tokens": output_tokens,
            "agent/cached_input_tokens": cached,
        }
        duration_ms = self.duration_ms
        if duration_ms is None:
            start, end = parse_time(self.started_at), parse_time(self.ended_at)
            if start and end:
                duration_ms = max(0, int((end - start).total_seconds() * 1000))
        if duration_ms is not None:
            values["agent/duration_s"] = round(duration_ms / 1000, 3)
        return values


def _claude_usage(usage: dict[str, Any]) -> dict[str, int]:
    uncached = int(usage.get("input_tokens") or 0)
    cache_read = int(usage.get("cache_read_input_tokens") or 0)
    cache_write = int(usage.get("cache_creation_input_tokens") or 0)
    return {
        "input_tokens": uncached + cache_read + cache_write,
        "output_tokens": int(usage.get("output_tokens") or 0),
        "cached_input_tokens": cache_read,
        "cache_write_input_tokens": cache_write,
    }


def _codex_usage(usage: dict[str, Any]) -> dict[str, int]:
    return {
        "input_tokens": int(usage.get("input_tokens") or 0),
        "output_tokens": int(usage.get("output_tokens") or 0),
        "cached_input_tokens": int(usage.get("cached_input_tokens") or 0),
        "reasoning_output_tokens": int(usage.get("reasoning_output_tokens") or 0),
    }


def _parse_claude(records: list[dict]) -> dict[str, Any]:
    session: dict[str, Any] = {"provider": "Claude Code", "turns": []}
    turns: list[_Turn] = session["turns"]
    current: _Turn | None = None
    subagent_tools = {"Task", "Agent"}
    for record in records:
        rtype = record.get("type")
        if rtype == "ai-title" and record.get("aiTitle"):
            session["title"] = str(record["aiTitle"])
        if record.get("cwd") and not session.get("cwd"):
            session["cwd"] = record["cwd"]
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        ts = logbook_trace._timestamp(record)
        session.setdefault("started_at", ts)
        role = message.get("role") or rtype
        blocks = logbook_trace._content_blocks(message.get("content"))
        sidechain = bool(record.get("isSidechain"))
        if role == "user":
            texts = [
                logbook_trace._text(b.get("text"))
                for b in blocks
                if b.get("type") == "text"
            ]
            prompt = "\n".join(t for t in texts if t and not _is_wrapper_text(t))
            if prompt.strip() and not sidechain and not record.get("isMeta"):
                current = _Turn(len(turns) + 1, ts, prompt.strip())
                turns.append(current)
            if current is None:
                continue
            for block in blocks:
                if block.get("type") == "tool_result":
                    current.finish_tool(
                        str(block.get("tool_use_id")),
                        logbook_trace._text(block.get("content")),
                        ts,
                        bool(block.get("is_error")),
                    )
            continue
        if role != "assistant" or current is None:
            continue
        model = message.get("model")
        if model == "<synthetic>":
            model = None
        parent = current.open_tool_parent(subagent_tools) if sidechain else None
        gen_id = str(message.get("id") or record.get("uuid") or ts)
        generation = current.add_generation(
            gen_id,
            model,
            _claude_usage(message["usage"]) if message.get("usage") else {},
            ts,
            parent_id=parent,
        )
        if model:
            session["model"] = model
        for block in blocks:
            btype = block.get("type")
            if btype == "text" and not sidechain:
                current.add_assistant_text(logbook_trace._text(block.get("text")), ts)
            elif btype == "tool_use":
                current.start_tool(
                    str(block.get("id")),
                    str(block.get("name") or "tool"),
                    block.get("input"),
                    ts,
                    parent_id=generation["id"],
                )
    return session


def _subagent_files(path: Path) -> list[tuple[int, str | None, Path]]:
    files = []
    for transcript in sorted((path.parent / path.stem / "subagents").glob("*.jsonl")):
        meta_path = transcript.with_suffix(".meta.json")
        meta: dict[str, Any] = {}
        if meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                meta = {}
        files.append(
            (int(meta.get("spawnDepth") or 1), meta.get("toolUseId"), transcript)
        )
    return sorted(files, key=lambda item: item[0])


def _attach_claude_subagents(session: dict[str, Any], path: Path) -> None:
    """Nest subagent transcripts (``<session>/subagents/agent-*.jsonl``) under
    the Agent/Task tool call that spawned them, as Claude Code writes them."""
    turns: list[_Turn] = session["turns"]
    for _, tool_use_id, transcript in _subagent_files(path):
        owner = next((t for t in turns if tool_use_id in t.tools), None)
        if owner is None:
            continue
        parent_id = owner.tools[tool_use_id]["id"]
        last_activity = owner.tools[tool_use_id].get("start_time")
        agent_key = transcript.stem
        for record in logbook_trace._records(transcript):
            message = record.get("message")
            if not isinstance(message, dict):
                continue
            ts = logbook_trace._timestamp(record)
            blocks = logbook_trace._content_blocks(message.get("content"))
            if message.get("role") == "user":
                for block in blocks:
                    if block.get("type") == "tool_result":
                        owner.finish_tool(
                            str(block.get("tool_use_id")),
                            logbook_trace._text(block.get("content")),
                            ts,
                            bool(block.get("is_error")),
                        )
                last_activity = ts or last_activity
                continue
            if message.get("role") != "assistant":
                continue
            model = message.get("model")
            if model == "<synthetic>":
                model = None
            gen_id = f"{agent_key}-{message.get('id') or record.get('uuid') or ts}"
            generation = owner.add_generation(
                gen_id,
                model,
                _claude_usage(message["usage"]) if message.get("usage") else {},
                ts,
                parent_id=parent_id,
                start=last_activity,
            )
            for block in blocks:
                if block.get("type") == "tool_use":
                    owner.start_tool(
                        str(block.get("id")),
                        str(block.get("name") or "tool"),
                        block.get("input"),
                        ts,
                        parent_id=generation["id"],
                    )
            last_activity = ts or last_activity


def _codex_output(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(
            logbook_trace._text(item.get("text") if isinstance(item, dict) else item)
            for item in value
        )
    return logbook_trace._text(value)


_EXIT_CODE = re.compile(
    r'\\?"exit_code\\?"\s*:\s*(-?\d+)|exit code:?\s*(-?\d+)|exited with code\s*(-?\d+)',
    re.IGNORECASE,
)


def _codex_tool_failed(output: str) -> bool | None:
    """Whether a Codex tool call failed, from the exit codes in its output.

    Returns None when the output carries no exit code, so the span is left
    without a status instead of being assumed successful.
    """
    codes = [int(next(g for g in m.groups() if g)) for m in _EXIT_CODE.finditer(output)]
    if not codes:
        return None
    return any(code != 0 for code in codes)


def _parse_codex(records: list[dict]) -> dict[str, Any]:
    session: dict[str, Any] = {"provider": "Codex", "turns": []}
    turns: list[_Turn] = session["turns"]
    current: _Turn | None = None
    pending_turn_id: str | None = None
    model: str | None = None
    has_usage_records = any(r.get("type") == "token_usage_record" for r in records)
    for record in records:
        rtype = record.get("type")
        payload = (
            record.get("payload") if isinstance(record.get("payload"), dict) else {}
        )
        ptype = payload.get("type")
        ts = logbook_trace._timestamp(record)
        if rtype == "session_meta":
            session["cwd"] = payload.get("cwd")
            session["started_at"] = ts or payload.get("timestamp")
            continue
        if rtype == "turn_context":
            model = payload.get("model") or model
            if model:
                session["model"] = model
            continue
        if rtype == "event_msg" and ptype == "task_started":
            pending_turn_id = payload.get("turn_id")
            current = None
            continue
        if rtype == "event_msg" and ptype in {"task_complete", "turn_aborted"}:
            if current is not None:
                if payload.get("duration_ms") is not None:
                    current.duration_ms = int(payload["duration_ms"])
                if ptype == "turn_aborted":
                    current.status = "aborted"
                current.touch(ts)
            continue
        if rtype == "token_usage_record" and current is not None:
            usage = payload.get("usage") or {}
            current.end_response(
                str(payload.get("response_id") or ts), model, _codex_usage(usage), ts
            )
            continue
        if (
            rtype == "event_msg"
            and ptype == "token_count"
            and not has_usage_records
            and current is not None
        ):
            usage = (payload.get("info") or {}).get("last_token_usage") or {}
            if usage:
                current.end_response(
                    f"{current.index}-{len(current.generations)}",
                    model,
                    _codex_usage(usage),
                    ts,
                )
            continue
        if rtype != "response_item":
            continue
        if ptype == "message":
            role = payload.get("role")
            text = "\n".join(
                logbook_trace._text(b.get("text"))
                for b in logbook_trace._content_blocks(payload.get("content"))
                if b.get("type") in {"input_text", "output_text", "text"}
            ).strip()
            if role == "user" and text and not _is_wrapper_text(text):
                current = _Turn(len(turns) + 1, ts, text)
                current.turn_id = pending_turn_id
                turns.append(current)
            elif role == "assistant" and current is not None:
                current.begin_response()
                current.add_assistant_text(text, ts)
        elif current is None:
            continue
        elif ptype == "reasoning":
            current.begin_response()
        elif ptype in {"function_call", "custom_tool_call", "local_shell_call"}:
            arguments = payload.get("input", payload.get("arguments"))
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    pass
            current.begin_response()
            current.response_tools.append(
                current.start_tool(
                    str(payload.get("call_id") or payload.get("id")),
                    str(payload.get("name") or ptype),
                    arguments,
                    ts,
                )
            )
        elif ptype in {"function_call_output", "custom_tool_call_output"}:
            output = _codex_output(payload.get("output"))
            current.finish_tool(
                str(payload.get("call_id")),
                output,
                ts,
                _codex_tool_failed(output),
            )
    return session


def load_session(path: str | Path) -> dict[str, Any]:
    """Parse a Claude Code or Codex session transcript into turns."""
    path = Path(path).expanduser()
    if not path.is_file():
        raise AgentSessionError(f"Session file not found: {path}")
    records = logbook_trace._records(path)
    provider = logbook_trace._detect_provider(records)
    if provider == "claude":
        session = _parse_claude(records)
        _attach_claude_subagents(session, path)
    elif provider == "codex":
        session = _parse_codex(records)
    else:
        raise AgentSessionError(
            f"Unsupported session format in {path}; supported: "
            + ", ".join(SUPPORTED_PROVIDERS.values())
        )
    session["session_id"] = logbook_trace._session_id(records, provider, path)
    return session


def run_identity(session: dict[str, Any]) -> tuple[str, str]:
    slug = PROVIDER_SLUGS[session["provider"]]
    prefix = RUN_NAME_PREFIXES[session["provider"]]
    session_id = session["session_id"]
    started = parse_time(session.get("started_at")) or datetime.now(timezone.utc)
    suffix = (re.sub(r"[^0-9a-zA-Z]", "", session_id) or session_id)[-6:]
    name = f"{prefix}-{started.strftime('%Y%m%d-%H%M')}-{suffix}"
    return f"{slug}-{session_id}", name


def turn_log_id(session: dict[str, Any], turn_index: int) -> str:
    return uuid.uuid5(
        _LOG_ID_NAMESPACE, f"{session['provider']}:{session['session_id']}:{turn_index}"
    ).hex


def build_log_entries(
    session: dict[str, Any],
    *,
    project: str,
    group: str | None = None,
    last: int | None = None,
    scrub: bool = True,
) -> list[dict[str, Any]]:
    """Turn a parsed session into ``/bulk_log`` entries, one per turn."""
    run_id, run_name = run_identity(session)
    turns: list[_Turn] = session["turns"]
    if last is not None:
        turns = turns[-last:] if last > 0 else []
    config = {
        "_Group": group or PROVIDER_SLUGS[session["provider"]],
        "_Created": session.get("started_at"),
        "agent": session["provider"],
        "session_id": session["session_id"],
        "model": session.get("model"),
        "cwd": session.get("cwd"),
        "title": session.get("title"),
    }
    config = {key: value for key, value in config.items() if value is not None}
    entries = []
    for turn in turns:
        metadata = {
            "agent": session["provider"],
            "session_id": session["session_id"],
            "turn": turn.index,
            "status": turn.spans()[0]["status"],
        }
        if turn.models:
            metadata["model"] = turn.models[-1]
        if turn.turn_id:
            metadata["turn_id"] = turn.turn_id
        if session.get("title"):
            metadata["session_title"] = session["title"]
        trace = Trace(
            messages=_clean(turn.messages, scrub),
            metadata=_clean(metadata, scrub),
            spans=_clean(turn.spans(), scrub),
        )
        metrics = {
            **turn.metrics(),
            TRACE_KEY: trace._to_dict(project, run_name, turn.index),
        }
        entries.append(
            {
                "project": project,
                "run": run_name,
                "run_id": run_id,
                "metrics": metrics,
                "step": turn.index,
                "timestamp": turn.started_at,
                "config": config if not entries else None,
                "log_id": turn_log_id(session, turn.index),
                "replace": True,
            }
        )
    return entries


def apply_final_reply(session: dict[str, Any], reply: str | None) -> None:
    """Fill in the last turn's reply from a Stop hook payload.

    Agents may fire the Stop hook before the transcript file contains the
    final assistant message; the hook payload carries it directly.
    """
    if not reply or not session["turns"]:
        return
    turn: _Turn = session["turns"][-1]
    if not turn.has_final_reply():
        turn.add_assistant_text(reply, turn.ended_at)


def write_entries(
    entries: list[dict[str, Any]],
    *,
    server_url: str | None = None,
    space_id: str | None = None,
) -> str:
    """Write entries locally, to a self-hosted server, or to a Space.

    Returns a short description of the destination.
    """
    if not entries:
        return "nothing to import"
    space_id, server_url = utils.resolve_space_id_and_server_url(space_id, server_url)
    if space_id is None and server_url is None:
        first = entries[0]
        SQLiteStorage.bulk_log(
            project=first["project"],
            run=first["run"],
            run_id=first["run_id"],
            metrics_list=[e["metrics"] for e in entries],
            steps=[e["step"] for e in entries],
            timestamps=[e["timestamp"] for e in entries]
            if all(e["timestamp"] for e in entries)
            else None,
            config=first["config"],
            log_ids=[e["log_id"] for e in entries],
            replace=True,
        )
        return "local database"

    if space_id is not None:
        hf_token = huggingface_hub.utils.get_token()
        client = RemoteClient(space_id, hf_token=hf_token, verbose=False)
        destination = f"Space {space_id}"
    else:
        base, url_token = utils.parse_trackio_server_url(server_url)
        write_token = url_token or os.environ.get("TRACKIO_WRITE_TOKEN")
        if not write_token:
            raise AgentSessionError(
                "Self-hosted logging requires a write token: add write_token to "
                "the server URL or set TRACKIO_WRITE_TOKEN."
            )
        hf_token = None
        client = RemoteClient(base, write_token=write_token, verbose=False)
        destination = base
    client.predict(api_name="/bulk_log", logs=entries, hf_token=hf_token)
    return destination


def read_hook_payload(stream=None) -> dict[str, Any]:
    stream = stream or sys.stdin
    raw = stream.read()
    if not raw.strip():
        raise AgentSessionError("No hook payload on stdin.")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AgentSessionError(f"Hook payload is not JSON: {exc}") from exc
    if not isinstance(payload, dict) or not payload.get("transcript_path"):
        raise AgentSessionError("Hook payload has no transcript_path.")
    return payload


def default_project(session: dict[str, Any], hook_payload: dict | None) -> str:
    cwd = (hook_payload or {}).get("cwd") or session.get("cwd")
    name = Path(cwd).name if cwd else ""
    return name or "agent-sessions"
