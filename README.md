<p align="center">
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="trackio/assets/trackio_logo_type_dark_transparent.png">
  <source media="(prefers-color-scheme: light)" srcset="trackio/assets/trackio_logo_type_light_transparent.png">
  <img width="75%" alt="Trackio Logo" src="trackio/assets/trackio_logo_type_light_transparent.png">
</picture>
  
</p>


<div align="center">


  
[![trackio-backend](https://github.com/gradio-app/trackio/actions/workflows/test.yml/badge.svg)](https://github.com/gradio-app/trackio/actions/workflows/test.yml)
[![PyPI downloads](https://img.shields.io/pypi/dm/trackio)](https://pypi.org/project/trackio/)
[![PyPI](https://img.shields.io/pypi/v/trackio)](https://pypi.org/project/trackio/)
![Python version](https://img.shields.io/badge/python-3.10+-important)
[![Twitter follow](https://img.shields.io/twitter/follow/trackioapp?style=social&label=follow)](https://twitter.com/trackioapp)

</div>

Welcome to `trackio`: a lightweight, <u>free</u> experiment tracking library built by Hugging Face for humans and AI agents 🤗. 

**Why Trackio when other experiment-tracking libraries exist?** Trackio has a few qualities that make it particularly useful for  agents: 
* It is local-first, because you shouldn't need to make an account to log data
* Logs are stored in SQLite database (with support for "freezing" logs to Parquet), which not only lets Trackio supports very high throughputs for parallel experiments, but also
* provides an easy CLI interface for querying data (including directly on the SQL data), perfect for LLM-driven analysis.

So whether you are using agents to run entire research experiments autonomously or whether you are just using LLMs to analyze data, Trackio is for you.

For human users, Trackio _also_ ships with a Gradio-inspired dashboard so you can view metrics, media, tables, alerts, etc.:



https://github.com/user-attachments/assets/2683cf27-7520-4fff-9ee9-bdc08a8ca404



### Trackio's main features:

- **API compatible** with `wandb.init`, `wandb.log`, and `wandb.finish`. Drop-in replacement: just 

  ```python
  import trackio as wandb
  ```
  and keep your existing logging code.

- **Local-first, cloud-optional** design: dashboard runs locally by default. But note that you can also log metrics to a Hugging Face Space with `space_id` which is _also_ free and useful for collaborative experiments.
- **LLM-friendly**: Built with autonomous ML experiments in mind, Trackio includes a CLI for programmatic access and a Python API for run management, making it easy for LLMs to log metrics and query experiment data.
  - Use `trackio query project --project <name> --sql "SELECT ..."` for read-only SQL when `trackio list` and `trackio get` are not enough
  - See the storage schema and direct query reference at https://huggingface.co/docs/trackio/storage_schema

- **Free**: Everything here, including hosting on Hugging Face, is free!

## Installation

Trackio requires [Python 3.10 or higher](https://www.python.org/downloads/). Install with `pip`:

```bash
pip install trackio
```

or with `uv`:

```bash
uv pip install trackio
```

### Installing the ap-mic-inc fork

This fork adds features that are not in the PyPI release:

| Feature | Where to find it |
| --- | --- |
| Claude Code and Codex sessions as traces (`trackio hooks install`, `trackio import agent-session`) | Traces page, [Coding-agent traces](#coding-agent-traces-claude-code-codex) |
| Automatic Hugging Face dataset lineage | Run and artifact Lineage, [Dataset lineage](#dataset-lineage) |
| Artifact lineage on every run | Runs → a run → Lineage |
| Per-project disk usage and free space | Settings → Storage |
| Dismissing alerts | Alert panel (needs write access) |
| Multi-node system metrics (one run per node, grouped) | System Metrics → Quickstart → Multi-node |
| Host, node rank, GPU models, driver/CUDA recorded per run | Run page → System; System Metrics → Nodes and per-host GPU filters; [Logging from a GPU machine](#logging-from-a-gpu-machine) |
| A Quickstart on every page, including storage limits and large-data tips | Top of each page |
| Markdown reports with tables, links, and code blocks | Alerts & Reports |
| Source revision in `trackio --version` and under the dashboard logo | See below |
| Fixes: Discord webhooks, `trackio.save()` paths, a path traversal in uploads, distinct trace ids, and more | — |

Install it from GitHub. Until these changes are merged into `main`, use the
feature branch:

```bash
pip install "trackio @ git+https://github.com/ap-mic-inc/trackio@feat/agent-traces-and-dashboard-fixes"
# after the merge:
pip install "trackio @ git+https://github.com/ap-mic-inc/trackio@main"
```

Installing from git builds the dashboard, so [Node.js](https://nodejs.org/) and
`npm` must be available (set `SKIP_FRONTEND_BUILD=1` only if you provide
`trackio/frontend/dist/` yourself). Use the fork both where you log (training
jobs, Claude Code or Codex) and where you run the dashboard: the server side is
what stores re-imported agent turns in place, lists monitoring-only nodes, and
serves the updated UI.

`trackio --version` prints the version with the source revision, e.g.
`trackio 0.39.0 (9945ca9)`, or `(9945ca9+3f2a1c)` for uncommitted changes. The
dashboard shows the same revision under the logo, so you can check that a
running server has picked up your changes.

## Usage

To get started, you can run a simple example that logs some fake training metrics:

```python
import trackio
import random
import time

runs = 3
epochs = 8


for run in range(runs):
    trackio.init(
        project="my-project",
        config={"epochs": epochs, "learning_rate": 0.001, "batch_size": 64}
    )

    for epoch in range(epochs):
        train_loss = random.uniform(0.2, 1.0)
        train_acc = random.uniform(0.6, 0.95)

        val_loss = train_loss - random.uniform(0.01, 0.1)
        val_acc = train_acc + random.uniform(0.01, 0.05)

        trackio.log({
            "epoch": epoch,
            "train_loss": train_loss,
            "train_accuracy": train_acc,
            "val_loss": val_loss,
            "val_accuracy": val_acc
        })

        time.sleep(0.2)

trackio.finish()
```

Running the above will print to the terminal instructions on launching the dashboard.

The usage of `trackio` is designed to be identical to `wandb` in most cases, so you can easily switch between the two libraries.

```py
import trackio as wandb
```

## Dashboard

You can launch the dashboard by running in your terminal:

```bash
trackio show
```

or, in Python:

```py
import trackio

trackio.show()
```

You can also provide an optional `project` name as the argument to load a specific project directly:

```bash
trackio show --project "my-project"
```

or, in Python:

```py
import trackio 

trackio.show(project="my-project")
```

You can also point Trackio at a custom static frontend directory:

```bash
trackio show --frontend ./my-trackio-frontend
```

```py
import trackio

trackio.show(frontend_dir="./my-trackio-frontend")
```

The directory only needs an `index.html` file. Trackio keeps serving the same backend API under `/api/*`, so you can replace the UI without forking the backend. If the directory is missing or invalid, Trackio falls back to a minimal starter template.

To make a custom frontend apply everywhere by default:

```bash
trackio config set frontend ./my-trackio-frontend
```

Reset it with:

```bash
trackio config unset frontend
```

## Running in the Cloud (Hugging Face Spaces)

When calling `trackio.init()`, by default the service will run locally and store project data on the local machine.

But if you pass a `space_id` to `init`, like:

```py
trackio.init(project="my-project", space_id="orgname/space_id")
```

or

```py
trackio.init(project="my-project", space_id="username/space_id")
```

it will use an existing or automatically deploy a new [Hugging Face Space](https://huggingface.co/spaces/) as needed. You should be logged in with the `huggingface-cli` locally and your token should have write permissions to create the Space.

You can view each Trackio Space individually, or all of your Trackio dashboards in one place: **https://trackio-laboratory.hf.space/**

## Self-hosted Trackio server

You can run the Trackio dashboard and API on your own machine or infrastructure and point training jobs at it over HTTP. Pass the write-access URL from `trackio.show()` (which may include `write_token` in the query), or a base URL plus the `TRACKIO_WRITE_TOKEN` environment variable. Set `TRACKIO_WRITE_TOKEN` before launching the server if you want to provide the server write token instead of using a random startup token. The client sends that token on requests; it is not your Hugging Face token.

```py
trackio.init(project="my-project", server_url="http://127.0.0.1:7860?write_token=YOUR_TOKEN")
```

You can also set `TRACKIO_SERVER_URL` (and optionally `TRACKIO_WRITE_TOKEN` if the URL has no query string). If `space_id` / `TRACKIO_SPACE_ID` and `server_url` / `TRACKIO_SERVER_URL` are both set, Trackio uses the Hugging Face Space and ignores the self-hosted URL.

### Getting the write token

By default anyone who can reach a self-hosted dashboard can read it (set
`TRACKIO_AUTH_REQUIRED=1`, or enable it on the Admin page, to require sign-in
for everything). Logging, uploads, dismissing alerts, and renaming or deleting
runs need write access, which comes from one of:

1. **The write token.** The server takes it from `TRACKIO_WRITE_TOKEN` when it
   starts, or generates a random one (a new one on every restart). `trackio
   show` prints the full link in its output:

   ```text
   * Trackio dashboard opened in browser with write access at: http://127.0.0.1:7860?write_token=...
   ```

   In Python, `trackio.show()` returns it as the fourth value
   (`app, url, share_url, full_url = trackio.show(block_thread=False)`). If
   someone else runs the server, ask them for this link or the token.
2. **Signing in** with an account that has the `write` or `admin` role: local
   accounts created on the Admin page (which you open with the write-token
   link), or OIDC when it is configured (see
   [OIDC authentication](docs/source/oidc_auth.md)).
3. **On Hugging Face Spaces**, signing in with a Hugging Face account that has
   write access to the Space.

How the token is sent:

- **Browser**: open the link once. The dashboard stores the token in a
  `trackio_write_token` cookie for 7 days and removes it from the address bar;
  after that, or after the server's token changes, open the link again.
  Without write access the dashboard is read-only and explains how to get it
  where an action needs it.
- **Training jobs, hooks, and scripts**: put it in the server URL
  (`server_url="http://host:7860?write_token=..."`) or set
  `TRACKIO_SERVER_URL` plus `TRACKIO_WRITE_TOKEN`. It is sent as the
  `X-Trackio-Write-Token` header.

Start long-running servers with a fixed token so restarts do not lock out
browsers, training jobs, and agent hooks, and keep it out of version control:

```bash
(umask 077; python -c "import secrets; print(secrets.token_urlsafe(32))" > ~/.trackio-write-token)
TRACKIO_WRITE_TOKEN=$(cat ~/.trackio-write-token) trackio show
```

Anyone with the token can write logs, change runs, and connect MCP tools, so
share it only with trusted users.

### Logging from a GPU machine

Training usually runs on a different machine than the dashboard. Keep one
dashboard, and have every GPU machine (or every node of a multi-node job) log
to it over HTTP.

**1. On the dashboard machine**, start the server with a fixed token (see
above). It listens on `127.0.0.1` only, so either keep it that way and use an
SSH tunnel from the GPU machine (step 2), or expose it on your network:

```bash
TRACKIO_WRITE_TOKEN=$(cat ~/.trackio-write-token) GRADIO_SERVER_PORT=7860 trackio show --host 0.0.0.0
```

Only expose it on a trusted network, and consider `TRACKIO_AUTH_REQUIRED=1` so
reading also needs sign-in.

**2. On the GPU machine**, install the fork with the GPU extra (NVML for GPU
metrics, psutil for CPU and memory) and check that it can reach the dashboard:

```bash
pip install "trackio[gpu] @ git+https://github.com/ap-mic-inc/trackio@feat/agent-traces-and-dashboard-fixes"
trackio --version        # should match the revision under the dashboard logo
nvidia-smi -L            # the GPUs Trackio will report

# If the server listens on 127.0.0.1, forward it over SSH (leave this running):
ssh -N -L 7860:127.0.0.1:7860 you@dashboard-host &
export TRACKIO_SERVER_URL=http://127.0.0.1:7860
# Otherwise point at it directly:
# export TRACKIO_SERVER_URL=http://dashboard-host:7860
export TRACKIO_WRITE_TOKEN=<token from step 1>

curl -s "$TRACKIO_SERVER_URL/version"
```

**3. Run a short smoke test** on the GPU machine. It keeps every GPU busy for a
minute if PyTorch is installed (otherwise it only logs a fake loss), and Trackio
records GPU and CPU metrics every 10 seconds plus the machine description:

```bash
python - <<'PY'
import math, time
import trackio

trackio.init(project="gpu-smoke-test", name=f"smoke-{time.strftime('%H%M%S')}")
try:
    import torch
    xs = [torch.randn(4096, 4096, device=f"cuda:{i}") for i in range(torch.cuda.device_count())]
except Exception:
    xs = []
start = time.time()
step = 0
while time.time() - start < 60:
    for x in xs:
        for _ in range(20):
            x @ x
    if xs:
        torch.cuda.synchronize()
    else:
        time.sleep(0.2)
    trackio.log({"train/loss": 2.0 * math.exp(-step / 2000)}, step=step)
    step += 1
trackio.finish()
PY
```

Then open the dashboard, pick the `gpu-smoke-test` project, and check:

- **System Metrics**: the Nodes table shows the machine's hostname and GPUs, and
  `gpu/…` charts (utilization, memory, power, temperature) appear with the GPU
  model next to each device in the sidebar.
- **Runs → the run → System**: host, GPU list with driver and CUDA versions,
  CPU, and Python/PyTorch versions.

**4. Multi-node jobs**: set the same `TRACKIO_SERVER_URL` and
`TRACKIO_WRITE_TOKEN` on every node, call `trackio.init()` on each node's local
rank 0 with a shared `group=` and a per-node `name=`, and log training metrics
from global rank 0 only. The full script is under System Metrics → Quickstart →
Multi-node. For example, on each of two nodes:

```bash
torchrun --nnodes 2 --nproc-per-node 8 --node-rank $NODE_RANK \
  --master-addr $MASTER_ADDR --master-port 29500 train.py
```

Each node's run records its hostname and node rank (from torchrun's
`GROUP_RANK` or Slurm's `SLURM_NODEID`), so the Nodes table lists the nodes in
order and the sidebar's device filter shows GPUs per host (`gpu-node-02 · GPU
0`), letting you look at one node's GPUs at a time.

**Troubleshooting**

| Symptom | Check |
| --- | --- |
| `Connection refused` / timeout | The server binds `127.0.0.1` unless started with `--host 0.0.0.0`; firewall; the SSH tunnel is still running. |
| `401` / `403`, or "write access" errors | `TRACKIO_WRITE_TOKEN` matches the server's; the server was restarted without a fixed token. |
| Run appears but no `gpu/` charts | `trackio[gpu]` (`nvidia-ml-py`) is installed and `nvidia-smi` works for this user; pass `auto_log_gpu=True` to force it. |
| No System section on the run page | The client is older than the dashboard (`trackio --version` on both), or `TRACKIO_LOG_DEVICE_INFO=0` is set. |
| Runs land in a local database instead of the dashboard | `TRACKIO_SERVER_URL` is not exported in the environment that starts training (e.g. inside `srun`/`torchrun` wrappers). |

See the documentation: [Self-host the Server](https://huggingface.co/docs/trackio/self_hosted_server).

## Syncing Offline Projects to Spaces

If you've been tracking experiments locally and want to move them to Hugging Face Spaces for sharing or collaboration, use the `sync` function:

```py
import trackio

trackio.sync(
    project="my-project",
    space_id="username/space_id",
    frontend_dir="./my-trackio-frontend",
)
```

This uploads your local project database to a new or existing Space. The Space will display all your logged experiments and metrics, and if a custom frontend is configured or passed explicitly it will be deployed there too.

Static Trackio Spaces (`sdk="static"`) are read-only browser-only snapshots, so their snapshot data must be public. Use the default Gradio Space for private dashboards; `sdk="static"` does not support `private=True`.

**Example workflow:**

```py
import trackio

# Start tracking locally
trackio.init(project="my-project", config={"lr": 0.001})
trackio.log({"loss": 0.5})
trackio.finish()

# Later, sync to Spaces
trackio.sync(
    project="my-project",
    space_id="username/my-experiments",
    frontend_dir="./my-trackio-frontend",
)
```

## Embedding a Trackio Dashboard

One of the reasons we created `trackio` was to make it easy to embed live dashboards on websites, blog posts, or anywhere else you can embed a website.

![image](https://github.com/user-attachments/assets/77f1424b-737b-4f04-b828-a12b2c1af4ef)

If you are hosting your Trackio dashboard on Spaces, then you can embed the url of that Space as an IFrame. You can even use query parameters to only specific projects and/or metrics, e.g.

```html
<iframe src="https://abidlabs-trackio-1234.hf.space/?project=my-project&metrics=train_loss,train_accuracy&sidebar=hidden" style="width:1600px; height:500px; border:0;">
```

Supported query parameters:

- `project`: (string) Open the dashboard on this project only. The project picker is hidden and the selection cannot be changed while this parameter is present (useful for embeds). The alias `selected_project` is accepted for the same behavior.
- `metrics`: (comma-separated list) Show only metrics whose names match exactly (after splitting on commas), e.g. `train_loss,train_accuracy`. Applied as the metrics filter on the Metrics page.
- `sidebar`: (string) One of `auto`, `visible`, `collapsed`, or `hidden`. The default is `auto`, which opens or collapses the sidebar based on the viewport width. **`visible`** starts with the full sidebar open, **`collapsed`** starts with only the narrow rail, and **`hidden`** removes the sidebar entirely. Explicit modes are not changed when the viewport is resized.
- `footer`: (string: "false"). When set to "false", hides the Gradio footer (Gradio-hosted Spaces). By default, the footer is visible.
- `xmin` / `xmax`: (numbers, use both together) Set the initial horizontal zoom range on the Metrics plots (shared x-axis window). Both must be valid numbers with `xmin < xmax`.
- `x_axis`: (string) Set the initial Metrics page x-axis, e.g. `step`, `time`, or a numeric logged metric/column such as `epoch`. The alias `x-axis` is also accepted. If the requested x-axis is unavailable, Trackio falls back to the default `step` axis.
- `smoothing`: (number) Set the initial value of the smoothing slider (0-20, where 0 = no smoothing).
- `plots_per_row`: (`auto` or integer from 1 to 6) Set the initial value of the **Plots per row** control. The default is `auto`, which fits plots to the available width.
- `accordion`: (string: "hidden"). When set to "hidden", hides the section header accordions around metric groups. By default, section headers are visible.
- `theme`: (string) Dashboard theme, e.g. `light` or `dark` (see theme behavior in the app).
- `write_token`: (string) One-time token written to a cookie for write access on Hugging Face Spaces deployments; stripped from the URL after load.

## Alerts

Trackio supports alerts that let you flag important events during training. Alerts are printed to the terminal, stored in the database, displayed in the dashboard, and optionally sent to webhooks (Slack, Discord, or any URL).

```python
import trackio

trackio.init(
    project="my-project",
    webhook_url="https://hooks.slack.com/services/T.../B.../xxx",
    webhook_min_level=trackio.AlertLevel.WARN,
)

for epoch in range(100):
    loss = train(...)
    trackio.log({"loss": loss})

    if epoch > 10 and loss > 5.0:
        trackio.alert(
            title="Loss spike",
            text=f"Loss jumped to {loss:.2f} at epoch {epoch}",
            level=trackio.AlertLevel.ERROR,
        )

trackio.finish()
```

You can query alerts via the CLI (`trackio get alerts --project "my-project" --json`), the Python API (`trackio.Api().alerts("my-project")`), or the HTTP endpoint (`/get_alerts`). For full details, see the [Alerts guide](https://huggingface.co/docs/trackio/alerts) and the [ML Agents guide](https://huggingface.co/docs/trackio/ml_agents).

## Dataset lineage

Hugging Face Hub datasets loaded with `datasets.load_dataset()` inside a run are
recorded automatically as the run's inputs, pinned to the dataset commit
(nothing is copied), so each run's Lineage shows which data it used. It is on
when `datasets` is imported before `trackio.init()`; control it with
`trackio.init(track_datasets=...)` or `TRACKIO_TRACK_DATASETS=0|1`. See the
[artifacts guide](docs/source/artifacts.md#tracking-hugging-face-datasets-automatically).

## Coding-agent traces (Claude Code, Codex)

Record every Claude Code or Codex turn as a trace: each session becomes a run,
and each prompt becomes a trace at `step` = turn, with the reply, every model call
(model and token usage), and every tool call (input, output, and whether it
failed), plus `agent/*` metrics per turn. Install the hooks from the repository
you want to trace:

```bash
trackio hooks install --claude --project my-repo   # Claude Code
trackio hooks install --codex --project my-repo    # Codex
trackio hooks install --claude --global            # every repository, one project each
trackio hooks uninstall --claude                   # remove
```

The command merges Trackio's hook into the agent's settings
(`.claude/settings.local.json` or `.codex/hooks.json`) without touching anything
else, and is safe to re-run. Codex only runs hooks you have trusted, so open
`/hooks` in Codex once after installing. Turns go to the local database, or to your server
when `TRACKIO_SERVER_URL` and `TRACKIO_WRITE_TOKEN` are set in the agent's
environment. Past sessions can be imported by hand:

```bash
trackio import agent-session ~/.claude/projects/<dir>/<session-id>.jsonl --project my-repo
```

Common secrets are redacted, but prompts, file contents, and command output are
kept, so only enable the hooks where you want sessions recorded. See the
[Traces guide](docs/source/traces.md#import-coding-agent-sessions-claude-code-codex)
for details.

## Examples

To get started and see basic examples of usage, see these files:

- [Basic example of logging metrics locally](https://github.com/gradio-app/trackio/blob/main/examples/fake-training.py)
- [Deploying the dashboard to Spaces](https://github.com/gradio-app/trackio/blob/main/examples/deploy-on-spaces.py)

## Throughput & Rate Limits

### Local logging

`trackio.log()` is a non-blocking call that appends to an in-memory queue and returns immediately. A background thread drains the queue every **0.5 s** and writes to the local SQLite database. Because log calls never touch the network or disk on the calling thread, the client-side throughput is effectively **unlimited** -- you can burst thousands of calls per second without slowing down your training loop.

Trackio is written defensively so Trackio-side failures should never take down your main experiment code. Under normal usage, issues inside Trackio's logging, flushing, or delivery paths degrade to warnings and local buffering rather than exceptions from your training loop.

### Logging to a Hugging Face Space

When a `space_id` is provided, the same background thread batches queued entries and pushes them to the Space via the Gradio client API. The main factors that affect end-to-end throughput are:

| Metric | Measured | Notes |
|---|---|---|
| **Burst from a single run** | **2,000 logs delivered in < 8 s** | `log()` calls themselves complete in ~0.01 s; the rest is network drain time. |
| **Parallel runs (32 threads)** | **32,000 logs (32 × 1,000) delivered in ~14 s wall time** | Each thread opens its own Gradio client connection to the Space. |
| **Logs per batch** | No hard cap | All entries queued during the 0.5 s interval are sent in a single `predict()` call. |
| **Data safety** | Zero-loss | If a batch fails to send, it is persisted to local SQLite and retried automatically when the connection recovers. |

These numbers were measured against a free-tier Hugging Face Space (2 vCPU / 16 GB RAM). Throughput will scale with the Space hardware tier, and local-only logging is orders of magnitude faster since no network round-trip is involved.

> **Tip:** For high-frequency logging (e.g. logging every training step), Trackio's queue-and-batch design means your training loop is never blocked by network I/O. Even if the Space is temporarily unreachable, logs accumulate locally and are replayed once the connection is restored.

### Trackio features (vs. W&B)

Trackio covers the core experiment-tracking workflow while staying lightweight, local-first, and easy to self-host. Here, we provide feature-by-feature comparison with W&B

<table>
  <thead>
    <tr>
      <th>Feature</th>
      <th align="center">Trackio</th>
      <th align="center">Weights &amp; Biases</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>Metrics, configs, and run tracking</td>
      <td align="center">✅</td>
      <td align="center">✅</td>
    </tr>
    <tr>
      <td>Live dashboards and run comparison</td>
      <td align="center">✅</td>
      <td align="center">✅</td>
    </tr>
    <tr>
      <td>Images, audio, and video</td>
      <td align="center">✅</td>
      <td align="center">✅</td>
    </tr>
    <tr>
      <td>Tables</td>
      <td align="center">✅</td>
      <td align="center">✅</td>
    </tr>
    <tr>
      <td>Automatic system metrics</td>
      <td align="center">✅</td>
      <td align="center">✅</td>
    </tr>
    <tr>
      <td>Alerts and webhooks</td>
      <td align="center">✅</td>
      <td align="center">✅</td>
    </tr>
    <tr>
      <td>Hosted dashboards and sharing</td>
      <td align="center">✅ Hugging Face Spaces</td>
      <td align="center">✅ W&B Cloud</td>
    </tr>
    <tr>
      <td>Versioned artifacts and lineage</td>
      <td align="center">✅</td>
      <td align="center">✅</td>
    </tr>
    <tr>
      <td>Experiment reports</td>
      <td align="center">✅</td>
      <td align="center">✅</td>
    </tr>
    <tr>
      <td>Artifact registry</td>
      <td align="center">✅</td>
      <td align="center">✅</td>
    </tr>
    <tr>
      <td><mark><strong>💸 Free for unlimited personal and team use?</strong></mark></td>
      <td align="center"><mark><strong>✅ YES</strong></mark></td>
      <td align="center"><mark><strong>❌ No!</strong></mark></td>
    </tr>
  </tbody>
</table>

Trackio is designed to be lightweight and _forkable_: **Python** for the backend and API, **Svelte 5** for the dashboard, so developers can fork the repository and extend either side.



## Note: Trackio is in Beta (DB Schema May Change)

Note that Trackio is in pre-release right now and we may release breaking changes. In particular, the schema of the Trackio sqlite database may change. Newer Trackio databases now use a stable `run_id` plus a non-unique `run_name`, while older databases remain readable in compatibility mode by treating `run_name` as the effective run identifier. Existing database files are located by default at: `~/.cache/huggingface/trackio`.  

The current SQLite and parquet layout is documented in the [Storage Schema and Direct Queries](https://huggingface.co/docs/trackio/storage_schema) guide, including examples for `trackio query`.

Since Trackio is in beta, your feedback is welcome! Please create issues with bug reports or feature requests.

## License

MIT License

## Documentation

The complete documentation and API reference for each version of Trackio can be found at: https://huggingface.co/docs/trackio/index

## Contribute

We welcome contributions to Trackio! Whether you're fixing bugs, adding features, or improving documentation, your contributions help make Trackio better for the entire machine learning community.

<p align="center">
  <img src="https://contrib.rocks/image?repo=gradio-app/trackio" />
</p>

To start contributing, see our [Contributing Guide](CONTRIBUTING.md).

### Development Setup

To set up Trackio for development, clone this repo and run:

```bash
pip install -e ".[dev,tensorboard]"
```

## Forking Trackio

Trackio is designed to be extremely forkable. The Trackio the **backend** is written in Python, and the built-in **dashboard** is **Svelte 5** under `trackio/frontend/` (with a production build bundled into the Python package). UI controls that mirror Gradio are implemented using **Gradio’s component source** as a starting point. You can fork the repo, change Python, frontend, or both (e.g. new dashboard pages, metrics, API routes), and see updates when running locally after installing in editable mode and rebuilding the frontend where needed.

If you deploy your Trackio dashboard to Hugging Face Spaces (by setting a `space_id` in `trackio.init()`), the Space UI reflects **your** checkout of Trackio—including any changes to the Python backend and the built Svelte assets.

To get started, follow the [Contributing Guide](#CONTRIBUTING.md) instructions to set up Trackio locally, then make your changes and run `trackio show` to preview them locally.

## Pronunciation

Trackio is pronounced TRACK-yo, as in "track yo' experiments"
