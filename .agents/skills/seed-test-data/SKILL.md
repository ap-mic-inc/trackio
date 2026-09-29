---
name: seed-test-data
description: Seed a Trackio project with rich, realistic test data (every Overview run state, grouped runs, nested configs, diverging/NaN runs, system metrics, multi-node device info, alerts, media, traces, artifacts, project files, live runs) for dashboard development. Use when asked to generate/add test data, demo data, fake runs, 測試資料, 假資料, or to populate a running dashboard.
---

# Seed rich test data

Use this skill when developing the dashboard and you need data that exercises
every UI path, or when asked to add test data to a Trackio server that is
already running.

The generator lives at `scripts/seed_rich_data.py` in this skill directory. Run
it from the repository root with the repo virtualenv (`python` may not be on
PATH):

```bash
.venv/bin/python .agents/skills/seed-test-data/scripts/seed_rich_data.py \
  --project rd-rich-demo [--reset] [--live-seconds 600] [--no-media] [--show]
```

| Flag | Effect |
| --- | --- |
| `--project` | Target project, default `rd-rich-demo` |
| `--reset` | Delete the project before seeding (destructive, confirm first on shared data) |
| `--seed` | RNG seed for reproducible curves |
| `--no-media` | Skip the showcase run (images, histograms, tables, reports, traces, artifacts) |
| `--no-files` | Skip the project files shown on the Files page |
| `--live-seconds N` / `--live-interval S` | Keep two `live-sft-seed*` runs logging for N seconds |
| `--show` | Launch a dashboard afterwards |

## Step 1: pick the target data directory

Data goes wherever `TRACKIO_DIR` points (default `~/.cache/huggingface/trackio`).

- **New sandbox**: set `TRACKIO_DIR` to a scratch directory and pass `--show`,
  or launch `TRACKIO_DIR=... GRADIO_SERVER_PORT=... .venv/bin/trackio show`.
- **Existing server on a port** (e.g. "add it to the one on 7876"): find the
  process and read its environment so the data lands in the directory that
  server reads:

  ```bash
  PORT=7876
  for pid in $(ss -ltnp | grep ":$PORT " | grep -o 'pid=[0-9]*' | cut -d= -f2 | sort -u); do
    tr '\0' ' ' < /proc/$pid/cmdline; echo
    readlink /proc/$pid/cwd
    tr '\0' '\n' < /proc/$pid/environ | grep -E 'TRACKIO|HF_HOME|GRADIO'
  done
  ```

  No `TRACKIO_DIR` means the default cache directory (or `$HF_HOME/trackio`).
  The server picks up new projects without a restart.

Prefer seeding a **new project** in that directory over writing into the
user's existing project; only mix into an existing project when asked.

## Step 2: seed

Run it in the background when using `--live-seconds`, so the turn is not
blocked:

```bash
TRACKIO_DIR=/path/from/step1 nohup .venv/bin/python \
  .agents/skills/seed-test-data/scripts/seed_rich_data.py \
  --project rd-rich-demo --live-seconds 600 > seed.log 2>&1 &
```

## Step 3: verify

```bash
TRACKIO_DIR=/path/from/step1 .venv/bin/python -c "
from trackio.sqlite_storage import SQLiteStorage as S
print(len(S.get_run_status('rd-rich-demo')))"
```

Expect 22 runs with `--live-seconds`, 20 without (17 with `--no-media`). For UI work, screenshot
`http://127.0.0.1:<port>/overview?project=rd-rich-demo` with Playwright (installed
in `.venv`) and look at it; add `?__theme=dark` for dark mode.

## What gets generated

- **Overview states**: live runs (Recent logs), runs ended 5 and 8 minutes ago
  (Quiet), runs ended hours to 12 days ago (No recent logs), and two config-only
  queued runs (Awaiting logs).
- **Groups**: `llm-sft`, `knowledge-distill`, `vision`, `rl-ppo`,
  `layout-edge-cases`, `showcase`, `live`, `multinode-pretrain`.
- **Configs**: nested dicts, lists and Chinese notes, for config search and
  run detail panels.
- **Metrics**: LLM SFT/distillation (`train/`, `eval/`, `distill/`, `perf/`),
  ImageNet classification (`val/`), PPO (`rollout/`); up to 1200 steps.
- **Edge cases**: loss divergence at step 300, NaN/Inf after step 200, a 3-step
  run, a very long run name, a Unicode/emoji run name.
- **System metrics**: CPU plus per-GPU utilization, memory, temperature, power.
- **Devices / multi-node**: every backdated run has a `_System` config block
  (host, CPU, GPU inventory) like `trackio.init()` records. The
  `multinode-pretrain` group is one 3-node job, `llama3-70b-pretrain-3node-node0..2`:
  node 0 logs training metrics, every node logs its own 4 GPUs, and node 2 has
  A100s instead of H100s, so System Metrics shows the Nodes table and "2 models"
  next to each GPU filter.
- **Alerts**: info, warn and error, with steps and backdated timestamps.
- **Showcase run**: images, histograms, tables, a markdown report, bilingual
  traces, and model and dataset artifacts.
- **Lineage chain** (group `lineage`): `lineage-eval-showcase-model` uses the
  showcase model and dataset and logs `eval-results`, which
  `lineage-build-report` uses to log `eval-report`, so run and artifact
  Lineage views show upstream and downstream neighbours.
- **Project files** (Files page, via `trackio.save`): nested `configs/`,
  `scripts/`, `notes/`, `results/` with every previewable text type, a Unicode
  file name with spaces, a 72 KB log past the 50,000-character preview limit,
  and binaries (a checkpoint, a PNG) that only offer download.

## How it works and how to extend it

`trackio.log()` always stamps the current time, so it cannot produce runs that
ended hours ago. The script writes backdated history directly through
`SQLiteStorage.bulk_log`, `bulk_log_system` and `bulk_alert`. Config-only runs
are inserted straight into the `configs` table. Only the showcase run uses the
public `trackio.init/log/log_artifact` API. If the storage schema changes,
update these calls.

Config dicts get `_Username`, `_Created` and `_Group` added, mirroring `Run`.

- **New scenario**: add an entry to `RUN_SPECS` with `name`, `group`, `kind`
  (`llm`, `vision` or `rl`), `steps`, `ended_ago`, `duration` and `config`.
  Optional keys are `diverge_at`, `nan_after` and `lr_scale`.
- **New metric family**: add a function to `METRIC_FNS`.
- **New Overview state**: tune `ended_ago` against the thresholds in
  `frontend/src/pages/Overview.svelte`, currently 120 s for live and 600 s
  for idle.

Follow the repo style: no inline comments, `ruff check --fix --select I && ruff
format` after editing.
