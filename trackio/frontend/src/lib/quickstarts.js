// Per-page Quickstart content rendered by components/Quickstart.svelte.
//
// Each guide builder takes the current project name and returns
// { eyebrow, title, badge, summary, description, items }, where each item is
// { id, label, code, hint, badge? }. `description` and `hint` are trusted, static
// HTML (inline markup such as <code>); the project name only lands in `code`,
// which is rendered as text.

function proj(project) {
  return project || "my-project";
}

export function overviewGuide(project) {
  const p = proj(project);
  return {
    eyebrow: "GET STARTED",
    title: "Quickstart",
    badge: "PYTHON",
    summary: "View starter code for logging runs",
    description: "Copy-paste snippets for logging from your training script.",
    items: [
      {
        id: "log",
        label: "Log metrics",
        code: `import trackio

trackio.init(
    project="${p}",
    name="my-run",
    config={"learning_rate": 1e-3, "epochs": 10},
)

for step in range(100):
    trackio.log({"train/loss": 1 / (step + 1)})

trackio.finish()`,
      },
      {
        id: "wandb",
        label: "Migrate from wandb",
        code: `import trackio as wandb

wandb.init(project="${p}", config={"learning_rate": 1e-3})
wandb.log({"train/loss": 0.42})
wandb.finish()`,
        hint: "Trackio is a drop-in replacement for <code>wandb</code>: change the import and keep the rest of your script.",
      },
      {
        id: "resume",
        label: "Resume a run",
        code: `import trackio

trackio.init(project="${p}", name="my-run", resume="allow")
trackio.log({"train/loss": 0.05})
trackio.finish()`,
        hint: '<code>resume</code> accepts <code>"never"</code> (default), <code>"allow"</code>, or <code>"must"</code>.',
      },
    ],
  };
}

export function metricsGuide(project) {
  const p = proj(project);
  return {
    eyebrow: "TRAINING PLAYBOOK",
    title: "LLM Training Recipes",
    badge: "4 STAGES",
    summary: "View metric recipes for pretraining, SFT, RL, and evals",
    description: `Stage-by-stage snippets for an LLM training pipeline, using the
      conventions this dashboard understands: metric prefixes like
      <code>train/</code>, <code>eval/</code>, and <code>perf/</code>
      become chart sections, and <code>group=</code> powers the sidebar's
      Group by. One project can hold every stage.`,
    items: [
      {
        id: "pretrain",
        label: "Pretraining",
        code: `import trackio

trackio.init(
    project="${p}",
    name="pretrain-7b-v1",
    group="pretrain",
    config={"params": "7B", "lr": 3e-4, "global_batch": 1024, "seq_len": 4096},
)

for step in range(total_steps):
    metrics = train_step()
    trackio.log({
        "train/loss": metrics.loss,
        "train/grad_norm": metrics.grad_norm,
        "lr": scheduler.get_last_lr()[0],
        "perf/tokens_per_s": metrics.tokens_per_s,
        "perf/step_time_s": metrics.step_time,
    }, step=step)

trackio.finish()`,
        hint: `Also worth tracking: <code>train/ppl</code>,
          <code>train/tokens_seen</code>, <code>perf/mfu</code>. Loss spikes
          are easiest to diagnose next to <code>train/grad_norm</code>, and
          GPU utilization is logged automatically when
          <code>nvidia-ml-py</code> is installed.`,
      },
      {
        id: "sft",
        label: "SFT",
        code: `import trackio

trackio.init(
    project="${p}",
    name="sft-v1",
    group="sft",
    config={"base_model": "pretrain-7b-v1", "lr": 2e-5, "epochs": 3},
)

for step, batch in enumerate(train_loader):
    loss = training_step(batch)
    trackio.log({"train/loss": loss, "lr": lr, "epoch": epoch}, step=step)
    if step % eval_every == 0:
        trackio.log({"eval/loss": evaluate()}, step=step)

trackio.finish()`,
        hint: `<code>eval/loss</code> rising while <code>train/loss</code> keeps
          falling is the overfitting signal to watch. Log
          <code>epoch</code> too so you can switch the X-axis to it.`,
      },
      {
        id: "rl",
        label: "RLHF / RL",
        code: `import trackio

trackio.init(
    project="${p}",
    name="grpo-v1",
    group="rl",
    config={"algo": "grpo", "kl_coef": 0.05, "rollouts_per_step": 1024},
)

for it in range(iterations):
    stats = rl_step()
    trackio.log({
        "train/reward": stats.mean_reward,
        "train/kl": stats.kl,
        "train/policy_loss": stats.policy_loss,
        "train/entropy": stats.entropy,
        "rollout/response_len": stats.mean_response_len,
        "rollout/accept_rate": stats.accept_rate,
    }, step=it)

trackio.finish()`,
        hint: `Healthy runs show <code>train/reward</code> climbing while
          <code>train/kl</code> stays bounded; collapsing
          <code>train/entropy</code> or exploding
          <code>rollout/response_len</code> are early failure signals.`,
      },
      {
        id: "evals",
        label: "Evals",
        code: `import trackio
import pandas as pd

trackio.init(
    project="${p}",
    name="eval-step-2000",
    group="eval",
    config={"checkpoint": "step-2000"},
)

trackio.log({"eval/mmlu": 0.62, "eval/gsm8k": 0.41, "eval/humaneval": 0.33})

df = pd.DataFrame({"prompt": prompts, "completion": completions, "score": scores})
trackio.log({"eval/samples": trackio.Table(dataframe=df)})

trackio.finish()`,
        hint: `One run per checkpoint (named after its step) keeps benchmarks
          comparable in the Runs table, and the samples table appears under
          Media &amp; Tables for side-by-side reading.`,
      },
    ],
  };
}

export function systemGuide(project) {
  const p = proj(project);
  return {
    eyebrow: "HARDWARE",
    title: "System Metrics",
    badge: "PYTHON",
    summary: "View code for logging GPU, CPU, custom, and multi-node system metrics",
    description: `System metrics are recorded against wall-clock time rather
      than training steps, so they keep flowing between <code>trackio.log()</code>
      calls and line up across runs.`,
    items: [
      {
        id: "auto",
        label: "Automatic",
        code: `import trackio

trackio.init(
    project="${p}",
    auto_log_gpu=True,       # default: on when nvidia-ml-py finds a GPU
    gpu_log_interval=10.0,   # seconds
    auto_log_cpu=True,       # default: on when psutil is installed
    cpu_log_interval=10.0,   # seconds
)

# ... training ...

trackio.finish()`,
        hint: `Install <code>pip install nvidia-ml-py psutil</code> and the defaults
          already do this; pass <code>False</code> to turn either off.`,
      },
      {
        id: "manual",
        label: "Log on demand",
        code: `import trackio

trackio.init(project="${p}", auto_log_gpu=False, auto_log_cpu=False)

for epoch in range(num_epochs):
    train_one_epoch()
    trackio.log_gpu()  # NVIDIA or Apple silicon, detected automatically
    trackio.log_cpu()  # CPU, RAM, disk and network I/O

trackio.finish()`,
        hint: "Useful when you only want a snapshot at specific points, such as the end of each epoch.",
      },
      {
        id: "custom",
        label: "Custom metrics",
        code: `import trackio

trackio.init(project="${p}")

trackio.log_system({
    "dataloader/queue_depth": loader.queue_depth,
    "storage/checkpoint_gb": checkpoint_size_gb,
})

trackio.finish()`,
        hint: "<code>trackio.log_system()</code> stores any values on the timestamp axis, next to the built-in hardware charts.",
      },
      {
        id: "multinode",
        label: "Multi-node",
        code: `# In the job script on every node (point all nodes at one Trackio server):
#   export TRACKIO_SERVER_URL="http://<dashboard-host>:7860"
#   export TRACKIO_WRITE_TOKEN="<token>"
import os
import socket

import trackio

rank = int(os.environ["RANK"])
local_rank = int(os.environ["LOCAL_RANK"])
node = os.environ.get("GROUP_RANK") or os.environ.get("SLURM_NODEID") or socket.gethostname()
experiment = "llama-sft-v3"

# One run per node, started by that node's local rank 0.
if local_rank == 0:
    trackio.init(
        project="${p}",
        group=experiment,             # Group by in the sidebar shows all nodes together
        name=f"{experiment}-node{node}",
    )

for step, batch in enumerate(train_loader):
    loss = training_step(batch)
    if rank == 0:                     # training metrics from global rank 0 only
        trackio.log({"train/loss": loss}, step=step)

if local_rank == 0:
    trackio.finish()`,
        hint: `<ul>
          <li><strong>Use one server for all nodes.</strong> Each node writes to
            its own local database by default. Set <code>TRACKIO_SERVER_URL</code>
            and <code>TRACKIO_WRITE_TOKEN</code> on every node so all runs land in
            one dashboard; don't share a SQLite file over NFS.</li>
          <li><strong>Start one run per node.</strong> The GPU monitor records
            every GPU on its machine, regardless of <code>CUDA_VISIBLE_DEVICES</code>,
            so call <code>trackio.init()</code> only on each node's local rank 0.
            Calling it on every rank records each GPU several times; calling it
            only on global rank 0 leaves the other nodes unmonitored.</li>
          <li><strong>Group the node runs.</strong> GPU metrics are named
            <code>gpu/0/…</code> without a hostname, so give each node its own
            run name and share <code>group=</code> to compare them side by side.</li>
          <li><strong>Log training metrics once.</strong> Call
            <code>trackio.log()</code> from global rank 0 only.</li>
          <li><strong>Keep the write token stable.</strong> Start the server with a
            fixed <code>TRACKIO_WRITE_TOKEN</code>; otherwise it changes on every
            restart and nodes lose write access.</li>
        </ul>`,
      },
    ],
  };
}

export function tracesGuide(project) {
  const p = proj(project);
  return {
    eyebrow: "LLM APPS & AGENTS",
    title: "Traces",
    badge: "PYTHON",
    summary: "View code for logging conversations, tool calls, and spans",
    description: `Log a <code>trackio.Trace</code> with OpenAI-style messages to
      inspect requests, tool calls, latency, tokens, and cost on this page.`,
    items: [
      {
        id: "chat",
        label: "Conversation",
        code: `import trackio

trackio.init(project="${p}")
trackio.log({
    "trace": trackio.Trace(
        messages=[
            {"role": "user", "content": "Find agent training datasets."},
            {"role": "assistant", "content": "Here are three datasets..."},
        ],
        metadata={"session_id": "session-123", "environment": "production"},
    )
})
trackio.finish()`,
      },
      {
        id: "tools",
        label: "Tool calls",
        code: `import trackio

trackio.init(project="${p}")
trackio.log({
    "trace": trackio.Trace(messages=[
        {"role": "user", "content": "What's the weather in Taipei?"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": "call_1",
                "type": "function",
                "function": {"name": "get_weather", "arguments": '{"city": "Taipei"}'},
            }],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": '{"temp_c": 29}'},
        {"role": "assistant", "content": "It's 29°C in Taipei."},
    ])
})
trackio.finish()`,
        hint: "Without explicit spans, the dashboard pairs <code>tool_calls</code> with their <code>tool</code> results into tool operations.",
      },
      {
        id: "spans",
        label: "Execution spans",
        code: `import trackio

trackio.init(project="${p}")
trackio.log({
    "trace": trackio.Trace(
        messages=messages,
        spans=[
            {"id": "root", "name": "answer-question", "kind": "span",
             "start_time": "2026-08-19T12:00:00Z", "end_time": "2026-08-19T12:00:03Z",
             "status": "success"},
            {"id": "gen-1", "parent_id": "root", "name": "llm-call", "kind": "generation",
             "model": "my-model", "duration_ms": 1200,
             "usage": {"input_tokens": 8439, "output_tokens": 188}, "cost_usd": 0.0042},
            {"id": "tool-1", "parent_id": "root", "name": "search", "kind": "tool",
             "input": {"query": "agent datasets"}, "output": {"hits": 3}},
        ],
    )
})
trackio.finish()`,
        hint: `Spans build the operation tree; <code>kind</code> is <code>span</code>,
          <code>generation</code>, or <code>tool</code>, and timing, usage, and cost
          roll up into the trace totals.`,
      },
    ],
  };
}

export function mediaGuide(project) {
  const p = proj(project);
  return {
    eyebrow: "RICH OUTPUTS",
    title: "Media & Tables",
    badge: "PYTHON",
    summary: "View code for logging images, audio, video, and tables",
    description: "Pass Trackio media objects to <code>trackio.log()</code> alongside your metrics; each key gets its own panel on this page.",
    items: [
      {
        id: "images",
        label: "Images",
        code: `import trackio

trackio.init(project="${p}")

for step in range(num_steps):
    trackio.log({
        "samples/generated": trackio.Image("sample.png", caption=f"step {step}"),
    }, step=step)

trackio.finish()`,
        hint: "<code>trackio.Image</code> also accepts a PIL image or a NumPy array. Logging the same key every few steps lets you scrub through training.",
      },
      {
        id: "av",
        label: "Audio & video",
        code: `import trackio

trackio.init(project="${p}")
trackio.log({
    "tts/sample": trackio.Audio("speech.wav"),
    "rollout/episode": trackio.Video("episode.mp4"),
})
trackio.finish()`,
      },
      {
        id: "tables",
        label: "Tables",
        code: `import pandas as pd
import trackio

trackio.init(project="${p}")

df = pd.DataFrame({"prompt": prompts, "completion": completions, "score": scores})
trackio.log({"eval/samples": trackio.Table(dataframe=df)})

trackio.finish()`,
      },
      {
        id: "other",
        label: "3D, HTML & Markdown",
        code: `import trackio

trackio.init(project="${p}")
trackio.log({
    "scene": trackio.Object3D("scene.glb"),
    "report/html": trackio.Html("<h1>Results</h1>"),
    "report/notes": trackio.Markdown("# Notes\\nLooks good."),
})
trackio.finish()`,
      },
    ],
  };
}

export function reportsGuide(project) {
  const p = proj(project);
  return {
    eyebrow: "NOTIFICATIONS",
    title: "Alerts & Reports",
    badge: "PYTHON",
    summary: "View code for firing alerts and logging reports",
    description: "Alerts flag problems as they happen; reports are Markdown summaries logged with the run.",
    items: [
      {
        id: "alert",
        label: "Fire an alert",
        code: `import trackio

trackio.init(project="${p}")

# ... inside your training loop ...
if val_loss > 2.0:
    trackio.alert(
        title="Validation loss spike",
        text=f"val_loss={val_loss:.4f} exceeded threshold 2.0",
        level=trackio.AlertLevel.ERROR,
    )`,
        hint: "Levels are <code>INFO</code>, <code>WARN</code> (default), and <code>ERROR</code>. Alerts are printed to the terminal and appear in the dashboard's alert panel.",
      },
      {
        id: "webhook",
        label: "Send to Slack / webhook",
        code: `import trackio

trackio.init(
    project="${p}",
    webhook_url="https://hooks.slack.com/services/...",
    webhook_min_level=trackio.AlertLevel.WARN,
)

trackio.alert("Training diverged", text="loss is NaN", level=trackio.AlertLevel.ERROR)`,
        hint: "Or set <code>TRACKIO_WEBHOOK_URL</code> and <code>TRACKIO_WEBHOOK_MIN_LEVEL</code>. A single alert can override the destination with <code>webhook_url=</code>.",
      },
      {
        id: "report",
        label: "Markdown report",
        code: `import trackio

trackio.init(project="${p}")
trackio.log({
    "reports/summary": trackio.Markdown(
        "# Run summary\\n\\n| Metric | Value |\\n| --- | --- |\\n| Final loss | 0.078 |"
    )
})
trackio.finish()`,
      },
    ],
  };
}

export function filesGuide(project) {
  const p = proj(project);
  return {
    eyebrow: "PROJECT FILES",
    title: "Files",
    badge: "PYTHON",
    summary: "View code for saving files to this project",
    description: "Files saved with <code>trackio.save()</code> belong to the project rather than a single run, which suits configs, scripts, and notes.",
    items: [
      {
        id: "save",
        label: "Save files",
        code: `import trackio

trackio.init(project="${p}")
trackio.save("config.yaml")
trackio.save("train.py")`,
      },
      {
        id: "glob",
        label: "Glob patterns",
        code: `import trackio

trackio.save("configs/*.yaml", project="${p}")
trackio.save("checkpoints/**/*.pt", project="${p}")`,
        hint: "Pass <code>project=</code> to save without an active run. For versioned outputs such as checkpoints, prefer Artifacts.",
      },
    ],
  };
}

export function artifactsGuide(project) {
  const p = proj(project);
  return {
    eyebrow: "VERSIONED OUTPUTS",
    title: "Artifacts",
    badge: "PYTHON",
    summary: "View code for logging and using versioned artifacts",
    description: "Artifacts are versioned files and directories with lineage: which run produced them, and which runs consumed them.",
    items: [
      {
        id: "log",
        label: "Log an artifact",
        code: `import trackio

trackio.init(project="${p}")

# ... training ...

trackio.log_artifact("checkpoints/", name="my-model", type="model")
trackio.finish()`,
        hint: "Each log under the same name creates the next version (<code>v0</code>, <code>v1</code>, ...) and moves the <code>latest</code> alias onto it.",
      },
      {
        id: "build",
        label: "Build with metadata",
        code: `import trackio

trackio.init(project="${p}")

artifact = trackio.Artifact(
    name="my-model",
    type="model",
    description="Fine-tuned on the v2 dataset",
    metadata={"base_model": "bert-base", "epochs": 3},
)
artifact.add_file("checkpoints/model.safetensors")
artifact.add_dir("tokenizer/")

trackio.log_artifact(artifact, aliases=["best"])
trackio.finish()`,
      },
      {
        id: "use",
        label: "Use an artifact",
        code: `import trackio

trackio.init(project="${p}", name="eval")

artifact = trackio.use_artifact("my-model:best", type="model")
path = artifact.download()

trackio.finish()`,
        hint: 'Resolve <code>"my-model"</code> (latest), a version like <code>"my-model:v2"</code>, or an alias. Using an artifact records the lineage edge.',
      },
    ],
  };
}
