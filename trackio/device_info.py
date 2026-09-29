"""Describe the machine a run executes on, recorded once at `trackio.init()`.

Stored in the run config under `_System` so multi-node runs can be told apart
(host, node rank, GPU inventory) and compared (drivers, CUDA, library
versions). Every probe is best effort: anything unavailable is left out.
GPU `index` values are physical NVML indices, which match the `gpu/<index>/`
keys the automatic GPU monitor logs.
"""

from __future__ import annotations

import os
import platform
import socket
import sys
from typing import Any

CONFIG_KEY = "_System"
ENV_VAR = "TRACKIO_LOG_DEVICE_INFO"
_FALSE = {"0", "false", "no", "off"}

_RANK_VARS = {
    "node_rank": ("GROUP_RANK", "NODE_RANK", "SLURM_NODEID"),
    "rank": ("RANK", "SLURM_PROCID"),
    "local_rank": ("LOCAL_RANK", "SLURM_LOCALID"),
    "world_size": ("WORLD_SIZE", "SLURM_NTASKS"),
    "local_world_size": ("LOCAL_WORLD_SIZE", "SLURM_NTASKS_PER_NODE"),
    "num_nodes": ("GROUP_WORLD_SIZE", "SLURM_NNODES", "SLURM_JOB_NUM_NODES"),
}


def should_log(log_device_info: bool | None) -> bool:
    if log_device_info is not None:
        return bool(log_device_info)
    return os.environ.get(ENV_VAR, "").strip().lower() not in _FALSE


def _first_int(names: tuple[str, ...]) -> int | None:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            try:
                return int(value.split("(")[0])
            except ValueError:
                continue
    return None


def _distributed() -> dict[str, int]:
    info = {}
    for key, names in _RANK_VARS.items():
        value = _first_int(names)
        if value is not None:
            info[key] = value
    return info


def _cpu() -> dict[str, Any]:
    info: dict[str, Any] = {"logical_cores": os.cpu_count()}
    model = None
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as f:
            for line in f:
                if line.lower().startswith("model name"):
                    model = line.split(":", 1)[1].strip()
                    break
    except OSError:
        pass
    model = model or platform.processor() or None
    if model:
        info["model"] = model
    try:
        import psutil  # noqa: PLC0415

        info["physical_cores"] = psutil.cpu_count(logical=False)
        info["memory_gb"] = round(psutil.virtual_memory().total / 1024**3, 1)
    except Exception:
        try:
            with open("/proc/meminfo", encoding="utf-8") as f:
                kb = int(f.readline().split()[1])
            info["memory_gb"] = round(kb / 1024**2, 1)
        except (OSError, ValueError, IndexError):
            pass
    return {k: v for k, v in info.items() if v is not None}


def _decode(value: Any) -> Any:
    return value.decode() if isinstance(value, bytes) else value


def _nvidia() -> dict[str, Any]:
    from trackio import gpu  # noqa: PLC0415

    if not gpu._init_nvml():
        return {}
    nvml = gpu._ensure_pynvml()
    info: dict[str, Any] = {}
    try:
        info["driver_version"] = _decode(nvml.nvmlSystemGetDriverVersion())
    except Exception:
        pass
    try:
        cuda = nvml.nvmlSystemGetCudaDriverVersion()
        info["cuda_driver_version"] = f"{cuda // 1000}.{(cuda % 1000) // 10}"
    except Exception:
        pass
    gpus = []
    try:
        count = nvml.nvmlDeviceGetCount()
    except Exception:
        count = 0
    for index in range(count):
        entry: dict[str, Any] = {"index": index}
        try:
            handle = nvml.nvmlDeviceGetHandleByIndex(index)
        except Exception:
            continue
        for key, probe in (
            ("name", lambda h: _decode(nvml.nvmlDeviceGetName(h))),
            ("uuid", lambda h: _decode(nvml.nvmlDeviceGetUUID(h))),
            (
                "memory_gb",
                lambda h: round(nvml.nvmlDeviceGetMemoryInfo(h).total / 1024**3, 1),
            ),
        ):
            try:
                entry[key] = probe(handle)
            except Exception:
                pass
        gpus.append(entry)
    if gpus:
        info["gpus"] = gpus
    visible = os.environ.get("CUDA_VISIBLE_DEVICES")
    if visible is not None:
        info["cuda_visible_devices"] = visible
    return info


def _libraries() -> dict[str, str]:
    versions = {"python": platform.python_version()}
    torch = sys.modules.get("torch")
    if torch is not None:
        versions["torch"] = str(getattr(torch, "__version__", ""))
        cuda = getattr(getattr(torch, "version", None), "cuda", None)
        if cuda:
            versions["torch_cuda"] = str(cuda)
    return versions


def collect() -> dict[str, Any]:
    """Best-effort description of this machine and process placement."""
    info: dict[str, Any] = {
        "hostname": socket.gethostname(),
        "os": platform.platform(),
    }
    probes = (
        ("distributed", _distributed),
        ("cpu", _cpu),
        ("gpu", _nvidia),
        ("versions", _libraries),
    )
    for key, probe in probes:
        try:
            value = probe()
        except Exception:
            continue
        if value:
            info[key] = value
    return info
