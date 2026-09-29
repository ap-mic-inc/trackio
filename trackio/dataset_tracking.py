"""Record Hugging Face Hub datasets loaded during a run as lineage inputs.

When enabled, every `datasets.load_dataset(...)` of a Hub dataset inside an
active run registers the dataset as a `dataset` artifact holding a single
reference, `hf://datasets/<repo>@<commit sha>`, and records it as an input of
the run. Nothing is downloaded or copied: the commit sha pins the exact data,
so a new commit becomes a new artifact version and repeated loads of the same
commit reuse it. The artifact has no producer run.

The hook wraps `datasets.load.load_dataset_builder`, which `load_dataset`
looks up at call time, so it also sees `from datasets import load_dataset`
bindings made before tracking started. Local data (e.g. `load_dataset("csv",
data_files=...)`) has no Hub repo and is skipped.
"""

from __future__ import annotations

import os
import re
import sys
from urllib.parse import quote

from trackio import context_vars
from trackio.artifact import Artifact

ENV_VAR = "TRACKIO_TRACK_DATASETS"
_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}
_installed = False
_warned = False


def should_track(track_datasets: bool | None) -> bool:
    """Resolve the init() setting: an explicit bool wins, then the environment
    variable, then "on if `datasets` is already imported" (no import cost)."""
    if track_datasets is not None:
        return bool(track_datasets)
    env = os.environ.get(ENV_VAR, "").strip().lower()
    if env in _TRUE:
        return True
    if env in _FALSE:
        return False
    return "datasets" in sys.modules


def artifact_name(repo_id: str, config: str | None = None) -> str:
    base = "hf-" + repo_id.replace("/", "--")
    if config and config != "default":
        base += f"--{config}"
    return re.sub(r"[^A-Za-z0-9._-]", "-", base)


def reference_uri(repo_id: str, revision: str | None) -> str:
    uri = f"hf://datasets/{repo_id}"
    if revision:
        uri += "@" + quote(revision, safe="")
    return uri


def record_hub_dataset(run, repo_id: str, config: str | None, revision: str | None):
    """Register the dataset version and link it to `run` as an input.
    Repeated loads of the same (repo, config, revision) in a run are no-ops."""
    key = (repo_id, config, revision)
    seen = run.__dict__.setdefault("_tracked_datasets", set())
    if key in seen:
        return None
    name = artifact_name(repo_id, config)
    metadata = {"source": "huggingface", "repo_id": repo_id, "revision": revision}
    if config and config != "default":
        metadata["config"] = config
    artifact = Artifact(
        name=name,
        type="dataset",
        description=f"Hugging Face dataset {repo_id}",
        metadata=metadata,
    )
    artifact.add_reference(reference_uri(repo_id, revision), checksum=False)
    logged = run.log_artifact(artifact, as_output=False)
    used = run.use_artifact(f"{name}:{logged.version}", type="dataset")
    seen.add(key)
    return used


def _on_builder(builder) -> None:
    global _warned
    run = context_vars.current_run.get()
    if run is None or not getattr(run, "_track_datasets", False):
        return
    repo_id = getattr(builder, "repo_id", None)
    if not repo_id:
        return
    config = getattr(getattr(builder, "config", None), "name", None)
    try:
        record_hub_dataset(run, repo_id, config, getattr(builder, "hash", None))
    except Exception as e:
        if not _warned:
            _warned = True
            print(
                f"* Warning: trackio could not record dataset {repo_id!r} for "
                f"lineage: {e}. Training continues; set {ENV_VAR}=0 to disable."
            )


def install() -> bool:
    """Wrap `datasets.load.load_dataset_builder` once. Returns False when the
    `datasets` library is not installed."""
    global _installed
    if _installed:
        return True
    try:
        import datasets.load as datasets_load  # noqa: PLC0415
    except ImportError:
        return False
    original = datasets_load.load_dataset_builder
    if getattr(original, "_trackio_wrapped", False):
        _installed = True
        return True

    def load_dataset_builder(*args, **kwargs):
        builder = original(*args, **kwargs)
        _on_builder(builder)
        return builder

    load_dataset_builder._trackio_wrapped = True
    load_dataset_builder.__wrapped__ = original
    load_dataset_builder.__doc__ = original.__doc__
    datasets_load.load_dataset_builder = load_dataset_builder
    _installed = True
    return True
