import trackio
from trackio import fragments
from trackio.sqlite_storage import SQLiteStorage


def test_system_only_run_is_listed_with_config(temp_dir):
    project = "multi_node"
    SQLiteStorage.bulk_log(
        project,
        "exp-node0",
        [{"train/loss": 0.5}],
        run_id="rid-node0",
        config={"_Group": "exp"},
    )
    SQLiteStorage.bulk_log_system(
        project,
        "exp-node1",
        [{"gpu/0/utilization": 90.0}],
        run_id="rid-node1",
        config={"_Group": "exp"},
    )

    records = SQLiteStorage.get_run_records(project)
    assert [(r["id"], r["name"]) for r in records] == [
        ("rid-node0", "exp-node0"),
        ("rid-node1", "exp-node1"),
    ]
    configs = SQLiteStorage.get_all_run_configs(project)
    assert configs["rid-node1"]["_Group"] == "exp"


def test_run_with_metrics_and_system_metrics_is_listed_once(temp_dir):
    project = "multi_node"
    SQLiteStorage.bulk_log(project, "exp", [{"loss": 1.0}], run_id="rid")
    SQLiteStorage.bulk_log_system(
        project, "exp", [{"cpu/utilization": 5}], run_id="rid"
    )
    assert [r["id"] for r in SQLiteStorage.get_run_records(project)] == ["rid"]


def test_artifact_link_does_not_duplicate_system_only_run(temp_dir):
    project = "multi_node"
    SQLiteStorage.bulk_log_system(
        project, "exp-node1", [{"cpu/utilization": 5}], run_id="rid-node1"
    )
    db_path = SQLiteStorage.get_project_db_path(project)
    with SQLiteStorage._get_connection(db_path) as conn:
        conn.execute(
            """INSERT INTO run_artifact_links
            (run_id, run_name, artifact_version_id, direction, created_at)
            VALUES (NULL, 'exp-node1', 1, 'output', '2026-01-01T00:00:00+00:00')"""
        )
        conn.commit()
    assert [r["name"] for r in SQLiteStorage.get_run_records(project)] == ["exp-node1"]


def test_log_system_only_run_persists_group(temp_dir):
    project = "multi_node_run"
    run = trackio.init(
        project=project,
        name="exp-node1",
        group="exp",
        config={"lr": 1e-4},
        auto_log_gpu=False,
        auto_log_cpu=False,
    )
    trackio.log_system({"gpu/0/utilization": 75.0})
    trackio.log_system({"gpu/0/utilization": 80.0})
    trackio.finish()

    assert [r["id"] for r in SQLiteStorage.get_run_records(project)] == [run.id]
    config = SQLiteStorage.get_all_run_configs(project)[run.id]
    assert config["_Group"] == "exp"
    assert config["lr"] == 1e-4
    assert len(SQLiteStorage.get_system_logs(project, "exp-node1", run_id=run.id)) == 2


def test_system_fragment_roundtrip_keeps_config(temp_dir):
    record = fragments.system_metric_record(
        {
            "project": "proj",
            "run": "run1",
            "run_id": "rid1",
            "metrics": {"gpu_util": 0.5},
            "timestamp": "2026-06-10T00:00:00+00:00",
            "config": {"_Group": "exp"},
            "log_id": "sys-0",
        }
    )
    parsed = fragments.parse_fragment_bytes(
        fragments.FragmentWriter.serialize_records([record])
    )
    assert fragments.import_records(parsed) == 1
    assert SQLiteStorage.get_all_run_configs("proj")["rid1"]["_Group"] == "exp"
    assert [r["id"] for r in SQLiteStorage.get_run_records("proj")] == ["rid1"]
