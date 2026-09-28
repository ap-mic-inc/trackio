"""
Seed a local project with varied, realistic data for dashboard development.

Covers every run state on the Overview page (recent logs, quiet, no recent logs,
awaiting logs), grouped runs, nested/searchable configs, diverging and NaN runs,
long histories, system metrics, alerts at every level, and a showcase run with
images, histograms, tables, markdown reports, traces and artifacts. Optionally
keeps a few runs logging live.

Usage:
    python .agents/skills/seed-test-data/scripts/seed_rich_data.py
    python .agents/skills/seed-test-data/scripts/seed_rich_data.py --project rd-demo --reset --live-seconds 600
    python .agents/skills/seed-test-data/scripts/seed_rich_data.py --no-media --show
"""

from __future__ import annotations

import argparse
import math
import os
import random
import sqlite3
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import orjson
from PIL import Image as PILImage
from PIL import ImageDraw

import trackio
from trackio.sqlite_storage import SQLiteStorage

USERNAME = "rd-seed"

RUN_SPECS = [
    {
        "name": "llama3-8b-sft-lr2e-5",
        "group": "llm-sft",
        "kind": "llm",
        "steps": 1200,
        "ended_ago": timedelta(hours=26),
        "duration": timedelta(hours=9),
        "config": {
            "model": {"arch": "llama3", "size": "8B", "lora": {"r": 16, "alpha": 32}},
            "optimizer": {"name": "adamw", "lr": 2e-5, "betas": [0.9, 0.95]},
            "dataset": "zh-tw-instruct-v3",
            "batch_size": 64,
            "seed": 42,
            "gpu": "H100x8",
            "tags": ["baseline", "sft"],
            "notes": "基準模型，繁中指令資料集",
        },
    },
    {
        "name": "llama3-8b-sft-lr5e-5",
        "group": "llm-sft",
        "kind": "llm",
        "steps": 1200,
        "ended_ago": timedelta(hours=20),
        "duration": timedelta(hours=9),
        "lr_scale": 1.4,
        "config": {
            "model": {"arch": "llama3", "size": "8B", "lora": {"r": 16, "alpha": 32}},
            "optimizer": {"name": "adamw", "lr": 5e-5, "betas": [0.9, 0.95]},
            "dataset": "zh-tw-instruct-v3",
            "batch_size": 64,
            "seed": 42,
            "gpu": "H100x8",
            "tags": ["sweep", "sft"],
        },
    },
    {
        "name": "llama3-8b-sft-lr1e-4-diverged",
        "group": "llm-sft",
        "kind": "llm",
        "steps": 420,
        "ended_ago": timedelta(hours=18),
        "duration": timedelta(hours=3),
        "diverge_at": 300,
        "config": {
            "model": {"arch": "llama3", "size": "8B", "lora": {"r": 16, "alpha": 32}},
            "optimizer": {"name": "adamw", "lr": 1e-4, "betas": [0.9, 0.95]},
            "dataset": "zh-tw-instruct-v3",
            "batch_size": 64,
            "seed": 7,
            "gpu": "H100x8",
            "tags": ["sweep", "failed"],
            "notes": "loss 在 step 300 附近發散",
        },
    },
    {
        "name": "qwen2.5-7b-distill-teacher-70b",
        "group": "knowledge-distill",
        "kind": "llm",
        "steps": 800,
        "ended_ago": timedelta(minutes=5),
        "duration": timedelta(hours=4),
        "config": {
            "model": {"arch": "qwen2.5", "size": "7B"},
            "teacher": {"arch": "llama3", "size": "70B", "temperature": 2.0},
            "optimizer": {"name": "adamw", "lr": 3e-5},
            "dataset": "knowledge-sdg-accepted",
            "kd_alpha": 0.7,
            "gpu": "A100x4",
            "tags": ["distill", "kd"],
        },
    },
    {
        "name": "resnet50-imagenet-mixup",
        "group": "vision",
        "kind": "vision",
        "steps": 90,
        "ended_ago": timedelta(days=3),
        "duration": timedelta(hours=30),
        "config": {
            "model": {"arch": "resnet50", "pretrained": False},
            "optimizer": {"name": "sgd", "lr": 0.1, "momentum": 0.9, "nesterov": True},
            "augment": {"mixup": 0.2, "cutmix": 1.0, "randaugment": "m9-n2"},
            "dataset": "imagenet-1k",
            "epochs": 90,
            "batch_size": 1024,
            "gpu": "A100x8",
            "tags": ["vision", "baseline"],
        },
    },
    {
        "name": "vit-b16-imagenet",
        "group": "vision",
        "kind": "vision",
        "steps": 300,
        "ended_ago": timedelta(hours=2),
        "duration": timedelta(hours=40),
        "config": {
            "model": {"arch": "vit-b16", "patch": 16, "dropout": 0.1},
            "optimizer": {"name": "adamw", "lr": 1e-3, "weight_decay": 0.05},
            "dataset": "imagenet-1k",
            "epochs": 300,
            "batch_size": 4096,
            "gpu": "TPUv4-128",
            "tags": ["vision"],
        },
    },
    {
        "name": "ppo-lunarlander-seed0",
        "group": "rl-ppo",
        "kind": "rl",
        "steps": 500,
        "ended_ago": timedelta(hours=6),
        "duration": timedelta(hours=1),
        "config": {
            "env": "LunarLander-v3",
            "algo": {"name": "ppo", "clip": 0.2, "gae_lambda": 0.95, "gamma": 0.99},
            "n_envs": 16,
            "seed": 0,
            "tags": ["rl"],
        },
    },
    {
        "name": "ppo-lunarlander-seed1",
        "group": "rl-ppo",
        "kind": "rl",
        "steps": 500,
        "ended_ago": timedelta(hours=5, minutes=30),
        "duration": timedelta(hours=1),
        "config": {
            "env": "LunarLander-v3",
            "algo": {"name": "ppo", "clip": 0.2, "gae_lambda": 0.95, "gamma": 0.99},
            "n_envs": 16,
            "seed": 1,
            "tags": ["rl"],
        },
    },
    {
        "name": "ppo-lunarlander-seed2-nan",
        "group": "rl-ppo",
        "kind": "rl",
        "steps": 240,
        "ended_ago": timedelta(hours=5),
        "duration": timedelta(minutes=30),
        "nan_after": 200,
        "config": {
            "env": "LunarLander-v3",
            "algo": {"name": "ppo", "clip": 0.2, "gae_lambda": 0.95, "gamma": 0.99},
            "n_envs": 16,
            "seed": 2,
            "tags": ["rl", "failed"],
        },
    },
    {
        "name": "tiny-smoke-test",
        "group": None,
        "kind": "llm",
        "steps": 3,
        "ended_ago": timedelta(minutes=45),
        "duration": timedelta(seconds=20),
        "config": {"smoke": True, "tags": ["ci"]},
    },
    {
        "name": (
            "an-extremely-long-run-name-for-layout-testing-"
            "bert-large-uncased-whole-word-masking-finetuned-squad-v2-fp16"
        ),
        "group": "layout-edge-cases",
        "kind": "llm",
        "steps": 150,
        "ended_ago": timedelta(minutes=8),
        "duration": timedelta(hours=1),
        "config": {"purpose": "long name overflow", "tags": ["edge-case"]},
    },
    {
        "name": "中文-實驗-名稱-🚀",
        "group": "layout-edge-cases",
        "kind": "vision",
        "steps": 60,
        "ended_ago": timedelta(days=12),
        "duration": timedelta(hours=2),
        "config": {"說明": "Unicode 與 emoji 測試", "tags": ["edge-case", "i18n"]},
    },
]

AWAITING_RUNS = [
    {
        "name": "queued-llama3-70b-sft",
        "group": "llm-sft",
        "config": {
            "model": {"arch": "llama3", "size": "70B"},
            "optimizer": {"name": "adamw", "lr": 1e-5},
            "gpu": "H100x32",
            "tags": ["queued"],
        },
    },
    {
        "name": "queued-ppo-seed3",
        "group": "rl-ppo",
        "config": {"env": "LunarLander-v3", "seed": 3, "tags": ["queued"]},
    },
]


def iso(dt: datetime) -> str:
    return dt.isoformat()


def noisy(value: float, scale: float, rng: random.Random) -> float:
    return value + rng.gauss(0, scale)


def llm_metrics(step: int, total: int, spec: dict, rng: random.Random) -> dict:
    progress = step / max(1, total - 1)
    lr_peak = spec["config"].get("optimizer", {}).get("lr", 3e-5)
    warmup = max(1, total // 20)
    if step < warmup:
        lr = lr_peak * step / warmup
    else:
        lr = (
            lr_peak * 0.5 * (1 + math.cos(math.pi * (step - warmup) / (total - warmup)))
        )
    scale = spec.get("lr_scale", 1.0)
    loss = 0.9 + 1.8 * math.exp(-4.5 * progress * scale) + rng.gauss(0, 0.04)
    grad_norm = abs(noisy(1.2 * math.exp(-2 * progress) + 0.3, 0.08, rng))
    diverge_at = spec.get("diverge_at")
    if diverge_at is not None and step >= diverge_at:
        blow = math.exp((step - diverge_at) / 25)
        loss *= blow
        grad_norm *= blow * 3
    metrics = {
        "train/loss": round(loss, 5),
        "train/learning_rate": lr,
        "train/grad_norm": round(grad_norm, 4),
        "perf/tokens_per_sec": round(noisy(52000, 1500, rng)),
        "train/epoch": round(progress * 3, 4),
    }
    if step % 50 == 0 or step == total - 1:
        metrics.update(
            {
                "eval/loss": round(loss + 0.08 + rng.gauss(0, 0.02), 5),
                "eval/perplexity": round(math.exp(min(loss + 0.08, 20)), 3),
                "eval/accuracy": round(
                    min(
                        0.95,
                        noisy(
                            0.35 + 0.5 * (1 - math.exp(-3.5 * progress * scale)),
                            0.012,
                            rng,
                        ),
                    ),
                    4,
                ),
                "eval/tmmlu_plus": round(
                    noisy(0.3 + 0.35 * (1 - math.exp(-3 * progress)), 0.01, rng), 4
                ),
            }
        )
    if "teacher" in spec["config"]:
        metrics["distill/kl_div"] = round(
            abs(noisy(2.5 * math.exp(-3 * progress), 0.05, rng)), 5
        )
        metrics["distill/student_teacher_agreement"] = round(
            min(0.99, noisy(0.4 + 0.55 * (1 - math.exp(-4 * progress)), 0.01, rng)), 4
        )
    return metrics


def vision_metrics(step: int, total: int, spec: dict, rng: random.Random) -> dict:
    progress = step / max(1, total - 1)
    return {
        "train/loss": round(noisy(0.8 + 5.5 * math.exp(-5 * progress), 0.05, rng), 4),
        "train/top1": round(
            min(0.99, noisy(0.1 + 0.72 * (1 - math.exp(-4 * progress)), 0.01, rng)), 4
        ),
        "val/top1": round(
            min(0.95, noisy(0.08 + 0.7 * (1 - math.exp(-4 * progress)), 0.008, rng)), 4
        ),
        "val/top5": round(
            min(0.99, noisy(0.3 + 0.63 * (1 - math.exp(-4 * progress)), 0.005, rng)), 4
        ),
        "train/learning_rate": spec["config"].get("optimizer", {}).get("lr", 0.1)
        * 0.5
        * (1 + math.cos(math.pi * progress)),
        "perf/images_per_sec": round(noisy(2900, 120, rng)),
    }


def rl_metrics(step: int, total: int, spec: dict, rng: random.Random) -> dict:
    progress = step / max(1, total - 1)
    reward = -200 + 470 * (1 - math.exp(-3.5 * progress)) + rng.gauss(0, 25)
    metrics = {
        "rollout/ep_rew_mean": round(reward, 2),
        "rollout/ep_len_mean": round(noisy(120 + 600 * progress, 30, rng), 1),
        "train/entropy_loss": round(noisy(-1.4 + 0.9 * progress, 0.03, rng), 4),
        "train/policy_gradient_loss": round(noisy(-0.01, 0.004, rng), 5),
        "train/value_loss": round(
            abs(noisy(80 * math.exp(-2 * progress) + 5, 4, rng)), 3
        ),
        "train/approx_kl": round(abs(noisy(0.012, 0.004, rng)), 5),
        "train/clip_fraction": round(min(1, abs(noisy(0.12, 0.03, rng))), 4),
    }
    nan_after = spec.get("nan_after")
    if nan_after is not None and step >= nan_after:
        metrics["train/value_loss"] = float("nan")
        metrics["train/approx_kl"] = float("inf")
    return metrics


METRIC_FNS = {"llm": llm_metrics, "vision": vision_metrics, "rl": rl_metrics}


def full_config(config: dict, group: str | None, created: datetime) -> dict:
    return {
        **config,
        "_Username": USERNAME,
        "_Created": iso(created),
        "_Group": group,
    }


def seed_backdated_run(
    project: str, spec: dict, now: datetime, rng: random.Random
) -> None:
    run_id = uuid.uuid4().hex
    steps = spec["steps"]
    end = now - spec["ended_ago"]
    start = end - spec["duration"]
    span = (end - start) / max(1, steps - 1)
    timestamps = [iso(start + span * i) for i in range(steps)]
    metric_fn = METRIC_FNS[spec["kind"]]
    metrics_list = [metric_fn(i, steps, spec, rng) for i in range(steps)]

    SQLiteStorage.bulk_log(
        project=project,
        run=spec["name"],
        run_id=run_id,
        metrics_list=metrics_list,
        steps=list(range(steps)),
        timestamps=timestamps,
        config=full_config(spec["config"], spec["group"], start),
    )

    n_sys = min(120, steps)
    sys_span = (end - start) / max(1, n_sys - 1)
    gpu_count = 8 if "x8" in str(spec["config"].get("gpu", "")) else 2
    system_list = []
    for i in range(n_sys):
        entry = {
            "cpu/percent": round(min(100, noisy(55, 8, rng)), 1),
            "cpu/memory_used_gb": round(noisy(180, 6, rng), 2),
        }
        for g in range(gpu_count):
            entry[f"gpu/{g}/utilization"] = round(
                min(100, max(0, noisy(92, 5, rng))), 1
            )
            entry[f"gpu/{g}/memory_used_gb"] = round(noisy(71, 1.5, rng), 2)
            entry[f"gpu/{g}/temperature_c"] = round(noisy(68 + g, 2, rng), 1)
            entry[f"gpu/{g}/power_w"] = round(noisy(610, 25, rng), 1)
        system_list.append(entry)
    SQLiteStorage.bulk_log_system(
        project=project,
        run=spec["name"],
        run_id=run_id,
        metrics_list=system_list,
        timestamps=[iso(start + sys_span * i) for i in range(n_sys)],
    )

    alerts = [
        (
            "Run started",
            f"{spec['name']} on {spec['config'].get('gpu', 'cpu')}",
            "info",
            0,
            start,
        )
    ]
    if spec.get("diverge_at") is not None:
        at = spec["diverge_at"]
        alerts.append(
            (
                "Loss spike detected",
                f"train/loss jumped at step {at + 20}",
                "warn",
                at + 20,
                start + span * (at + 20),
            )
        )
        alerts.append(
            (
                "Training diverged",
                "Loss exceeded 1e3, job aborted",
                "error",
                steps - 1,
                end,
            )
        )
    if spec.get("nan_after") is not None:
        at = spec["nan_after"]
        alerts.append(
            (
                "NaN in value_loss",
                "Detected non-finite value loss; check reward scaling",
                "error",
                at,
                start + span * at,
            )
        )
    if "failed" not in spec["config"].get("tags", []):
        alerts.append(
            ("Run finished", f"Completed {steps} steps", "info", steps - 1, end)
        )
    SQLiteStorage.bulk_alert(
        project=project,
        run=spec["name"],
        run_id=run_id,
        titles=[a[0] for a in alerts],
        texts=[a[1] for a in alerts],
        levels=[a[2] for a in alerts],
        steps=[a[3] for a in alerts],
        timestamps=[iso(a[4]) for a in alerts],
    )


def seed_awaiting_run(project: str, spec: dict, now: datetime) -> None:
    db_path = SQLiteStorage.init_db(project)
    config = full_config(spec["config"], spec["group"], now)
    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(configs)")}
        payload = orjson.dumps(config)
        if "run_id" in columns:
            conn.execute(
                "INSERT OR REPLACE INTO configs (run_id, run_name, config, created_at) VALUES (?, ?, ?, ?)",
                (uuid.uuid4().hex, spec["name"], payload, iso(now)),
            )
        else:
            conn.execute(
                "INSERT OR REPLACE INTO configs (run_name, config, created_at) VALUES (?, ?, ?)",
                (spec["name"], payload, iso(now)),
            )


def make_sample_image(step: int, size: int = 160) -> PILImage.Image:
    img = PILImage.new("RGB", (size, size), (18, 18, 28))
    draw = ImageDraw.Draw(img)
    for k in range(6):
        angle = step * 0.4 + k * math.pi / 3
        x = size / 2 + (size / 3) * math.cos(angle)
        y = size / 2 + (size / 3) * math.sin(angle)
        color = (80 + 30 * k, 200 - 25 * k, 120 + step * 10 % 120)
        draw.ellipse((x - 12, y - 12, x + 12, y + 12), fill=color)
    draw.text((8, 8), f"step {step}", fill=(240, 240, 240))
    return img


TRACE_EXAMPLES = [
    (
        "什麼是知識蒸餾？",
        "知識蒸餾是讓小模型（學生）學習大模型（教師）輸出分佈的技術。",
        0.94,
    ),
    (
        "Summarize Trackio in one sentence.",
        "Trackio is a local-first, wandb-compatible experiment tracker.",
        0.97,
    ),
    ("台灣最高的山是？", "玉山，海拔約 3,952 公尺。", 0.99),
    (
        "Write a haiku about loss curves.",
        "Descending slowly / gradients whisper through nights / plateau, then silence",
        0.71,
    ),
    ("2 的 10 次方是多少？", "1024。", 0.99),
]


def seed_showcase_run(project: str, steps: int = 40) -> None:
    rng = np.random.default_rng(0)
    trackio.init(
        project=project,
        name="showcase-all-media-types",
        group="showcase",
        config={
            "model": {"arch": "qwen2.5", "size": "1.5B"},
            "optimizer": {"name": "adamw", "lr": 1e-4},
            "dataset": "knowledge-sdg-accepted",
            "tags": ["showcase", "media", "traces"],
            "notes": "包含圖片、直方圖、表格、報告、Trace 與 Artifact",
        },
        auto_log_gpu=False,
        auto_log_cpu=False,
    )
    trackio.alert(
        title="Showcase run started",
        text="Logging every media type",
        level=trackio.AlertLevel.INFO,
    )

    for step in range(steps):
        payload = {
            "train/loss": float(2.0 * math.exp(-step / 12) + rng.normal(0, 0.03)),
            "train/accuracy": float(
                min(0.98, 0.4 + step * 0.015 + rng.normal(0, 0.01))
            ),
            "weights/layer0": trackio.Histogram(
                rng.normal(0, 1.0 * math.exp(-step / 30), 2000), num_bins=40
            ),
            "grads/layer0": trackio.Histogram(
                rng.laplace(0, 0.1 * math.exp(-step / 20), 2000), num_bins=40
            ),
        }
        if step % 5 == 0:
            payload["samples/generated"] = trackio.Image(
                make_sample_image(step), caption=f"step {step}"
            )
            payload["eval/predictions"] = trackio.Table(
                columns=[
                    "id",
                    "question",
                    "prediction",
                    "label",
                    "confidence",
                    "correct",
                ],
                data=[
                    [
                        f"q{step}-{i}",
                        q,
                        a,
                        a if c > 0.8 else "—",
                        round(c - 0.01 * i, 3),
                        c > 0.8,
                    ]
                    for i, (q, a, c) in enumerate(TRACE_EXAMPLES)
                ],
            )
        if step % 4 == 0:
            q, a, c = TRACE_EXAMPLES[(step // 4) % len(TRACE_EXAMPLES)]
            payload["agent/trace"] = trackio.Trace(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful bilingual assistant.",
                    },
                    {"role": "user", "content": q},
                    {"role": "assistant", "content": a},
                ],
                metadata={
                    "confidence": c,
                    "step": step,
                    "judge": "accepted" if c >= 0.85 else "rejected",
                },
            )
        if step == 10:
            trackio.alert(
                title="Accuracy plateau",
                text="train/accuracy flat for 5 steps",
                level=trackio.AlertLevel.WARN,
            )
        trackio.log(payload, step=step)

    trackio.log(
        {
            "reports/summary": trackio.Markdown(
                f"""# Showcase 報告

| Metric | Value |
| --- | --- |
| Steps | {steps} |
| Final loss | ~{2.0 * math.exp(-(steps - 1) / 12):.3f} |

- 圖片每 5 步一次
- Trace 每 4 步一次
- 兩個 histogram：`weights/layer0`、`grads/layer0`
"""
            )
        },
        step=steps - 1,
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "model.safetensors").write_bytes(rng.bytes(64 * 1024))
        (tmp_path / "config.json").write_text('{"arch": "qwen2.5", "size": "1.5B"}')
        artifact = trackio.Artifact(
            "showcase-model", type="model", metadata={"step": steps - 1}
        )
        artifact.add_file(tmp_path / "model.safetensors")
        artifact.add_file(tmp_path / "config.json")
        trackio.log_artifact(artifact, aliases=["best"])
        dataset_file = tmp_path / "eval.jsonl"
        dataset_file.write_text(
            "\n".join(f'{{"q": "{q}", "a": "{a}"}}' for q, a, _ in TRACE_EXAMPLES)
        )
        trackio.log_artifact(dataset_file, name="eval-set", type="dataset")

    trackio.finish()


PROJECT_FILES = {
    "configs/train.yaml": "model: qwen2.5-7b\nlr: 2.0e-5\nepochs: 3\nbatch_size: 64\n",
    "configs/eval.yaml": "benchmarks: [mmlu, gsm8k, humaneval]\nshots: 5\n",
    "configs/deepspeed.json": '{\n  "zero_optimization": {"stage": 3},\n  "bf16": {"enabled": true}\n}\n',
    "scripts/train.py": "import trackio\n\ntrackio.init(project='demo')\ntrackio.log({'loss': 0.1})\ntrackio.finish()\n",
    "scripts/launch.sh": "#!/usr/bin/env bash\ntorchrun --nnodes 2 --nproc-per-node 8 scripts/train.py\n",
    "notes/README.md": "# 實驗筆記\n\n| Run | 結果 |\n| --- | --- |\n| sft-v1 | baseline |\n",
    "notes/實驗紀錄 2026-09.txt": "中文檔名與空白的檔案，用來測試路徑編碼。\n",
    "results/metrics.csv": "step,loss,accuracy\n0,2.10,0.12\n100,0.84,0.61\n200,0.41,0.83\n",
    "results/summary.json": '{"best_step": 200, "accuracy": 0.83}\n',
    "results/predictions.tsv": "id\tprediction\tlabel\n1\tcat\tcat\n2\tdog\tcat\n",
}


def seed_project_files(project: str, rng: np.random.Generator) -> int:
    """Save project-level files covering every Files-page preview path:
    text formats, nested folders, a Unicode file name, a text file past the
    50,000-character preview limit, and binaries that only offer download."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for relative, content in PROJECT_FILES.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        long_log = "\n".join(
            f"step {i:05d} loss={2.0 * math.exp(-i / 800):.5f}" for i in range(3000)
        )
        (root / "logs").mkdir()
        (root / "logs" / "train.log").write_text(long_log, encoding="utf-8")
        (root / "checkpoints").mkdir()
        (root / "checkpoints" / "model-step-200.pt").write_bytes(rng.bytes(256 * 1024))
        image = PILImage.new("RGB", (64, 64), (249, 115, 22))
        image.save(root / "results" / "confusion-matrix.png")
        previous = Path.cwd()
        os.chdir(root)
        try:
            trackio.save("**/*", project=project)
        finally:
            os.chdir(previous)
        return sum(1 for f in root.rglob("*") if f.is_file())


def live_runs(project: str, seconds: int, interval: float, now: datetime) -> None:
    runs = []
    for i in range(2):
        name = f"live-sft-seed{i}"
        run_id = uuid.uuid4().hex
        config = full_config(
            {
                "model": {"arch": "llama3", "size": "8B"},
                "optimizer": {"name": "adamw", "lr": 3e-5},
                "live": True,
                "tags": ["live"],
                "seed": i,
            },
            "live",
            now,
        )
        runs.append(
            {"name": name, "run_id": run_id, "config": config, "rng": random.Random(i)}
        )
    deadline = time.time() + seconds
    step = 0
    while time.time() < deadline:
        stamp = iso(datetime.now(timezone.utc))
        for run in runs:
            rng = run["rng"]
            SQLiteStorage.bulk_log(
                project=project,
                run=run["name"],
                run_id=run["run_id"],
                metrics_list=[
                    {
                        "train/loss": round(
                            0.9 + 1.5 * math.exp(-step / 200) + rng.gauss(0, 0.03), 5
                        ),
                        "train/grad_norm": round(abs(rng.gauss(0.8, 0.1)), 4),
                        "perf/tokens_per_sec": round(rng.gauss(50000, 1200)),
                    }
                ],
                steps=[step],
                timestamps=[stamp],
                config=run["config"] if step == 0 else None,
            )
            SQLiteStorage.bulk_log_system(
                project=project,
                run=run["name"],
                run_id=run["run_id"],
                metrics_list=[
                    {"gpu/0/utilization": round(min(100, rng.gauss(90, 4)), 1)}
                ],
                timestamps=[stamp],
            )
        step += 1
        time.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--project", default="rd-rich-demo")
    parser.add_argument(
        "--reset", action="store_true", help="delete the project before seeding"
    )
    parser.add_argument("--seed", type=int, default=1234)
    parser.add_argument(
        "--no-media",
        action="store_true",
        help="skip the showcase media/trace/artifact run",
    )
    parser.add_argument(
        "--no-files",
        action="store_true",
        help="skip the project files shown on the Files page",
    )
    parser.add_argument(
        "--live-seconds",
        type=int,
        default=0,
        help="keep live runs logging for N seconds",
    )
    parser.add_argument("--live-interval", type=float, default=2.0)
    parser.add_argument(
        "--show", action="store_true", help="launch the dashboard afterwards"
    )
    args = parser.parse_args()

    if args.reset:
        trackio.delete_project(args.project, force=True)

    rng = random.Random(args.seed)
    now = datetime.now(timezone.utc)

    for spec in RUN_SPECS:
        seed_backdated_run(args.project, spec, now, rng)
        print(
            f"seeded {spec['name']} ({spec['steps']} steps, ended {spec['ended_ago']} ago)"
        )
    for spec in AWAITING_RUNS:
        seed_awaiting_run(args.project, spec, now)
        print(f"seeded awaiting run {spec['name']}")

    if not args.no_media:
        seed_showcase_run(args.project)
        print("seeded showcase-all-media-types")

    if not args.no_files:
        count = seed_project_files(args.project, np.random.default_rng(args.seed))
        print(f"seeded {count} project files")

    if args.show:
        trackio.show(project=args.project, open_browser=False, block_thread=False)

    if args.live_seconds > 0:
        print(f"live logging for {args.live_seconds}s …")
        live_runs(args.project, args.live_seconds, args.live_interval, now)

    print(f"done: trackio show --project {args.project}")
    if args.show and args.live_seconds <= 0:
        time.sleep(3600)


if __name__ == "__main__":
    main()
