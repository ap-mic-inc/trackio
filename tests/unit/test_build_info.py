import subprocess

from trackio import build_info


def _fake_git(outputs):
    def fake(*args):
        return outputs.get(args[0], b"")

    return fake


def test_git_revision_clean(monkeypatch, tmp_path):
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(build_info, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        build_info, "_git", _fake_git({"rev-parse": b"abc1234\n", "diff": b""})
    )
    build_info.git_revision.cache_clear()
    assert build_info.git_revision() == "abc1234"
    assert build_info.version_string("1.2.3") == "1.2.3 (abc1234)"
    build_info.git_revision.cache_clear()


def test_git_revision_dirty_depends_on_diff(monkeypatch, tmp_path):
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(build_info, "_REPO_ROOT", tmp_path)
    revisions = []
    for diff in (b"diff one", b"diff two"):
        monkeypatch.setattr(
            build_info, "_git", _fake_git({"rev-parse": b"abc1234\n", "diff": diff})
        )
        build_info.git_revision.cache_clear()
        revisions.append(build_info.git_revision())
    build_info.git_revision.cache_clear()
    assert all(r.startswith("abc1234+") and len(r) == 14 for r in revisions)
    assert revisions[0] != revisions[1]


def test_git_revision_not_a_checkout(monkeypatch, tmp_path):
    monkeypatch.setattr(build_info, "_REPO_ROOT", tmp_path)
    build_info.git_revision.cache_clear()
    assert build_info.git_revision() is None
    assert build_info.version_string("1.2.3") == "1.2.3"
    build_info.git_revision.cache_clear()


def test_git_missing(monkeypatch, tmp_path):
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(build_info, "_REPO_ROOT", tmp_path)

    def boom(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", boom)
    build_info.git_revision.cache_clear()
    assert build_info.git_revision() is None
    build_info.git_revision.cache_clear()


def test_git_revision_includes_untracked_files(monkeypatch, tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "new.py").write_text("v1")
    monkeypatch.setattr(build_info, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        build_info,
        "_git",
        _fake_git({"rev-parse": b"abc1234\n", "diff": b"", "ls-files": b"new.py\0"}),
    )
    build_info.git_revision.cache_clear()
    first = build_info.git_revision()
    (tmp_path / "new.py").write_text("v2")
    build_info.git_revision.cache_clear()
    second = build_info.git_revision()
    build_info.git_revision.cache_clear()
    assert first.startswith("abc1234+")
    assert first != second
