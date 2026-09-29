import types

import trackio
from trackio import device_info, gpu
from trackio.sqlite_storage import SQLiteStorage


class FakeNvml:
    def nvmlSystemGetDriverVersion(self):
        return b"550.54.15"

    def nvmlSystemGetCudaDriverVersion(self):
        return 12040

    def nvmlDeviceGetCount(self):
        return 2

    def nvmlDeviceGetHandleByIndex(self, index):
        return index

    def nvmlDeviceGetName(self, handle):
        return b"NVIDIA H100 80GB HBM3"

    def nvmlDeviceGetUUID(self, handle):
        return f"GPU-{handle}"

    def nvmlDeviceGetMemoryInfo(self, handle):
        return types.SimpleNamespace(total=80 * 1024**3)


def test_collect_reads_placement_and_gpus(monkeypatch):
    for name in ("GROUP_RANK", "NODE_RANK", "SLURM_NODEID", "SLURM_PROCID"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NODE_RANK", "2")
    monkeypatch.setenv("RANK", "17")
    monkeypatch.setenv("WORLD_SIZE", "32")
    monkeypatch.setenv("SLURM_NNODES", "4")
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0,1")
    monkeypatch.setattr(gpu, "_init_nvml", lambda: True)
    monkeypatch.setattr(gpu, "_ensure_pynvml", lambda: FakeNvml())

    info = device_info.collect()

    assert info["hostname"]
    assert info["distributed"]["node_rank"] == 2
    assert info["distributed"]["rank"] == 17
    assert info["distributed"]["world_size"] == 32
    assert info["distributed"]["num_nodes"] == 4
    assert info["gpu"]["driver_version"] == "550.54.15"
    assert info["gpu"]["cuda_driver_version"] == "12.4"
    assert info["gpu"]["cuda_visible_devices"] == "0,1"
    assert info["gpu"]["gpus"] == [
        {
            "index": 0,
            "name": "NVIDIA H100 80GB HBM3",
            "uuid": "GPU-0",
            "memory_gb": 80.0,
        },
        {
            "index": 1,
            "name": "NVIDIA H100 80GB HBM3",
            "uuid": "GPU-1",
            "memory_gb": 80.0,
        },
    ]
    assert info["versions"]["python"]


def test_collect_survives_failing_probes(monkeypatch):
    monkeypatch.setattr(gpu, "_init_nvml", lambda: False)

    def broken():
        raise RuntimeError("no /proc")

    monkeypatch.setattr(device_info, "_cpu", broken)
    info = device_info.collect()
    assert "cpu" not in info and "gpu" not in info
    assert info["hostname"]


def test_should_log_resolution(monkeypatch):
    monkeypatch.delenv("TRACKIO_LOG_DEVICE_INFO", raising=False)
    assert device_info.should_log(None) is True
    monkeypatch.setenv("TRACKIO_LOG_DEVICE_INFO", "0")
    assert device_info.should_log(None) is False
    assert device_info.should_log(True) is True


def test_init_stores_system_config(temp_dir, monkeypatch):
    monkeypatch.setattr(device_info, "collect", lambda: {"hostname": "node-a"})
    run = trackio.init(project="dev", auto_log_gpu=False, auto_log_cpu=False)
    trackio.log({"loss": 1.0})
    trackio.finish()
    assert SQLiteStorage.get_all_run_configs("dev")[run.id]["_System"] == {
        "hostname": "node-a"
    }

    run = trackio.init(
        project="dev", auto_log_gpu=False, auto_log_cpu=False, log_device_info=False
    )
    trackio.log({"loss": 1.0})
    trackio.finish()
    assert "_System" not in SQLiteStorage.get_all_run_configs("dev")[run.id]

