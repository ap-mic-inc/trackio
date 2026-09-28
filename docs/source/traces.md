# Traces

Trackio traces capture a user request, the assistant response, and the operations
that produced it. Open the **Traces** page in the dashboard to search requests,
inspect model and tool operations, and see latency, token, cost, and status totals.

## Log a conversation

Pass a [`Trace`](./api#trace) to `trackio.log()` with OpenAI-style
messages:

```python
import trackio

trackio.init(project="research-agent")
trackio.log(
    {
        "trace": trackio.Trace(
            messages=[
                {"role": "user", "content": "Find agent training datasets."},
                {"role": "assistant", "content": "Here are three datasets..."},
            ],
            metadata={"session_id": "session-123", "environment": "production"},
        )
    }
)
trackio.finish()
```

Messages can include `tool_calls` and `tool` results. When a trace has no explicit
spans, the dashboard pairs those calls and results into tool operations for easier
inspection.

## Add execution spans

Use `spans` when you need timings, hierarchy, model usage, cost, or operation
status. Each span is a dictionary. The minimal fields are `id`, `name`, and `kind`:

```python
trackio.Trace(
    messages=messages,
    spans=[
        {
            "id": "research",
            "name": "answer-research-question",
            "kind": "span",
            "start_time": "2026-08-19T12:00:00Z",
            "end_time": "2026-08-19T12:00:03Z",
            "status": "success",
        },
        {
            "id": "generation-1",
            "parent_id": "research",
            "name": "provider-request",
            "kind": "generation",
            "start_time": "2026-08-19T12:00:00Z",
            "end_time": "2026-08-19T12:00:01.2Z",
            "model": "my-model",
            "input": {"messages": messages},
            "output": {"text": "I will search for datasets."},
            "usage": {"input_tokens": 8439, "output_tokens": 188},
            "cost_usd": 0.0042,
            "status": "success",
        },
        {
            "id": "tool-1",
            "parent_id": "research",
            "name": "hf search",
            "kind": "tool",
            "start_time": "2026-08-19T12:00:01.3Z",
            "end_time": "2026-08-19T12:00:02Z",
            "input": {"query": "agent training datasets"},
            "output": {"datasets": ["example/dataset"]},
            "status": "success",
        },
    ],
)
```

Supported span fields:

| Field | Description |
|---|---|
| `id` | Identifier unique within the trace |
| `parent_id` | Optional parent span ID; creates the execution tree |
| `name` | Operation name shown in the inspector |
| `kind` | `span`, `generation`, or `tool` |
| `start_time`, `end_time` | ISO-8601 timestamps used to derive latency |
| `duration_ms` | Optional duration when timestamps are unavailable |
| `status` | Usually `success` or `error` |
| `error` | Structured or textual error details |
| `input`, `output` | Any JSON-serializable operation payload |
| `model` | Model identifier for a generation |
| `usage` | `input_tokens`, `output_tokens`, and optional `total_tokens` |
| `cost_usd` | Cost for this operation in US dollars |
| `metadata` | Additional operation metadata |

Trace latency is wall-clock time from the earliest span start to the latest span
end; when no span carries an `end_time`, the longest single `duration_ms` is used
instead. Token and cost totals sum the values on individual spans, so `usage` and
`cost_usd` should describe the local operation rather than a parent aggregate — a
parent that repeats its children's totals will double-count. Trackio does not
maintain a model pricing catalog; instrumentation should supply the actual cost.

A span is reported as failed when its `status` is `error` or `failed`, or when it
carries an `error`. For spans derived from messages, a tool result marks its
operation failed when the message sets `is_error`, `error`, or an error `status`;
OpenAI-style tool results carry no success signal, so those operations are left
without a status rather than assumed successful.

## Import coding-agent sessions (Claude Code, Codex)

`trackio import agent-session` turns a Claude Code or Codex session transcript into
traces, so you can review what a coding agent did turn by turn:

- the session becomes one run (grouped as `claude-code` or `codex`);
- every turn — one prompt and everything the agent did until it replied — becomes
  one trace at `step` = turn number, with the prompt and final reply as messages,
  one `generation` span per model call (model and token usage), and one `tool`
  span per tool call (input, output, and whether it failed);
- per-turn counters are logged as metrics: `agent/tool_calls`, `agent/tool_errors`,
  `agent/model_calls`, `agent/input_tokens`, `agent/cached_input_tokens`,
  `agent/output_tokens`, and `agent/duration_s`.

Import a transcript by hand:

```sh
trackio import agent-session ~/.claude/projects/<dir>/<session-id>.jsonl --project my-repo
trackio import agent-session ~/.codex/sessions/2026/09/28/rollout-<id>.jsonl --project my-repo
```

The project defaults to the name of the session's working directory. Imports are
idempotent: run and log ids are derived from the session id, and re-importing a
session updates its turns in place, so it is safe to import the same file after
every turn. Common secrets are redacted before anything is stored (pass
`--no-scrub` to keep the transcript as is); prompts, file contents, and command
output are still included, so only import sessions you want recorded.

### Collect every turn automatically

Install the hooks from the repository you want to trace:

```sh
trackio hooks install --claude --project my-repo   # Claude Code
trackio hooks install --codex --project my-repo    # Codex
```

Claude Code hooks go to `.claude/settings.local.json` (personal, not committed)
and Codex hooks to `.codex/hooks.json`; `--global` installs them in
`~/.claude/settings.json` or `~/.codex/hooks.json` instead, so every repository
is traced into a project named after its folder. The command merges into
existing settings without touching other hooks, points the hook at the
`trackio` executable it was run from, and is safe to re-run. Preview with
`--dry-run`, and remove the hooks with `trackio hooks uninstall --claude` or
`--codex`.

Codex silently skips hooks that you have not trusted, so nothing is recorded
until you open `/hooks` in Codex and trust the Trackio hook (a repository's hooks
also need the project to be trusted). Trust is recorded against the hook's exact
definition, so trust it again after re-running `trackio hooks install` with
different options. For `codex exec` automation you can pass
`--dangerously-bypass-hook-trust` instead.

When a turn ends, the agent runs `trackio import agent-session --hook` with the
transcript path on stdin. It imports the latest turns (`--all` for the whole
session), fills in the final reply from the payload when the transcript has not
caught up yet, and never fails the agent: errors are printed to stderr and the
command exits 0. The Stop hook runs synchronously (about a second per turn)
because headless runs such as `claude -p` exit as soon as the reply is printed,
which would kill a background hook.

To add the hooks by hand instead, Claude Code in `.claude/settings.local.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "trackio import agent-session --hook --project my-repo",
            "timeout": 30
          }
        ]
      }
    ],
    "SessionEnd": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "trackio import agent-session --hook --all --project my-repo",
            "timeout": 60
          }
        ]
      }
    ]
  }
}
```

and Codex in `.codex/hooks.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "trackio import agent-session --hook --project my-repo",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

Imports go to the local database by default. Set `TRACKIO_SERVER_URL` and
`TRACKIO_WRITE_TOKEN` (or pass `--server-url`) to send them to a self-hosted
server, or `TRACKIO_SPACE_ID` (or `--space`) for a Space. If `trackio` is installed
in a virtualenv, use the absolute path to its `trackio` executable in `command`
(`trackio hooks install` does this for you).

## Inspect traces from the CLI

The dashboard is not the only way to read traces back. The CLI works against
local data, or against a Space with `--space`:

```bash
trackio list traces --project research-agent
trackio list traces --project research-agent --search "rate limit"
trackio get trace --project research-agent --trace-id <id>
trackio get trace-summary --project research-agent
```

`trackio get trace` prints the execution tree with per-span latency, model,
tokens, cost, and errors. `trackio get trace-summary` groups every span by
operation name and reports calls, errors, average and worst-case latency, token
usage, and cost — useful for finding which operation dominates spend or fails
most often. Both accept `--json`.

For anything else, `spans` is a JSON column, so `json_each` works with
[`trackio query project`](./cli_commands):

```bash
trackio query project --project research-agent --sql "
SELECT json_extract(s.value, '\$.name') AS operation,
       SUM(COALESCE(json_extract(s.value, '\$.usage.input_tokens'), 0)) AS input_tokens
FROM traces, json_each(traces.spans) AS s
GROUP BY operation ORDER BY input_tokens DESC"
```

## Viewing traces on the Hugging Face Hub

Every logged trace is also written as an agent session `.jsonl` file, in the
format the Hub's agent trace viewer renders. When Trackio runs on a Space, the
bucket is mounted at `/data`, so these land in the bucket under
`traces/{project}/{run}/{trace_id}.jsonl` — open one from the bucket's file
browser to step through the conversation, its tool calls, and their results.

Trackio emits [Pi's session
format](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/session-format.md)
(version 3), which the Hub supports natively. The Hub also documents a Session
Trace Simple Format, but files written to that spec are not currently rendered
by the viewer.

The session files are a rendering artifact, never the source of truth. The
`traces` table stays authoritative, and everything else on this page — search,
the span tree, `trace-summary`, direct SQL — reads from it. What the session
file carries is the linear conversation, enriched from the spans with the
details the viewer can display:

| From the span | Appears in the session as |
|---|---|
| `model` on a generation | a `model_change` entry |
| `usage`, `cost_usd` | `usage` on the assistant turn it produced |
| `status`, `error` on a tool | `isError` on the tool result |
| `input`, `output` on a tool | the `toolCall` arguments and result, for traces with no `messages` |

Token usage is paired with the assistant turn that produced it rather than
repeated on every turn, so the viewer does not double-count. Span hierarchy,
`duration_ms`, per-span `metadata`, and the `kind` of non-tool spans have no
place in the format and stay in SQLite.

Session files sit beside the `trackio/` prefix rather than inside it, so
`trackio` CLI commands that sync a bucket down do not pull a second copy of
every trace. Set `TRACKIO_TRACE_SESSIONS_DIR` to write them somewhere else.

## Trace-level metadata

Spans are the preferred source for latency, cost, and status. When a trace has no
spans, or its spans omit these values, the dashboard falls back to these
`metadata` keys:

| Key | Used for |
|---|---|
| `status` | Trace status, unless a span reports an error |
| `duration_ms`, `latency_ms` | Trace latency |
| `cost_usd` | Trace cost, when no span reports a cost |

## Search

Trace search matches message content, trace metadata, and each span's `id`,
`name`, `kind`, `model`, `status`, `error`, and `metadata`. Span `input` and
`output` payloads are not indexed: they routinely repeat the whole conversation
for every generation, so indexing them would multiply stored trace size for
little search value.

Nested Trackio media values in messages, metadata, span input, or span output are
stored alongside the trace, and images are rendered inline in the inspector.
