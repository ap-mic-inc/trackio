import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

import trackio
from trackio import utils
from trackio.media.utils import get_project_media_path


def _saved(project):
    root = utils.project_media_dir(project) / "files"
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs" / "train.yaml").write_text("lr: 1")
    (tmp_path / "notes.md").write_text("# notes")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_save_without_run_keeps_relative_paths(temp_dir, workspace):
    trackio.save("**/*", project="files-no-run")
    assert _saved("files-no-run") == ["configs/train.yaml", "notes.md"]


def test_save_with_run_keeps_relative_paths(temp_dir, workspace):
    trackio.init(project="files-run", auto_log_gpu=False, auto_log_cpu=False)
    trackio.save("**/*")
    trackio.finish()
    assert _saved("files-run") == ["configs/train.yaml", "notes.md"]


@pytest.mark.parametrize("bad", ["../escape", "a/../../b", "/etc", "..\\\\x"])
def test_media_path_rejects_escaping_relative_paths(temp_dir, bad):
    with pytest.raises(ValueError):
        get_project_media_path("p", relative_path=bad)


def test_server_upload_places_files_and_blocks_traversal(temp_dir, tmp_path):
    project = "files-upload"
    source = tmp_path / "train.yaml"
    source.write_text("lr: 2")
    _, url, _, full_url = trackio.show(block_thread=False, open_browser=False)
    token = parse_qs(urlparse(full_url).query)["write_token"][0]
    headers = {"x-trackio-write-token": token}
    base = url.rstrip("/")

    def upload(relative_path):
        with source.open("rb") as handle:
            staged = httpx.post(
                f"{base}/api/upload",
                headers=headers,
                files={"files": (source.name, handle)},
                timeout=5,
            ).json()["paths"][0]
        return httpx.post(
            f"{base}/api/bulk_upload_media",
            headers=headers,
            json={
                "uploads": [
                    {
                        "project": project,
                        "run": None,
                        "step": None,
                        "relative_path": relative_path,
                        "uploaded_file": {"path": staged, "orig_name": "train.yaml"},
                    }
                ],
                "hf_token": None,
            },
            timeout=5,
        )

    assert upload("configs").status_code == 200
    assert upload("legacy/train.yaml").status_code == 200
    assert _saved(project) == ["configs/train.yaml", "legacy/train.yaml"]

    escaped = upload("../../../outside")
    assert escaped.status_code == 400
    outside = utils.MEDIA_DIR.parent / "outside"
    assert not outside.exists()
    assert not any("outside" in str(p) for p in Path(utils.MEDIA_DIR).rglob("*")), (
        os.listdir(utils.MEDIA_DIR)
    )
