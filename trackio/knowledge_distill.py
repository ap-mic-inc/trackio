"""Small, deterministic helpers for tracking knowledge distillation jobs.

The module deliberately does not call an LLM.  A coding agent or skill can
produce candidate JSONL records, then use :func:`distill_jsonl` to apply the
repeatable acceptance rules and record provenance in Trackio.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import trackio


def _normalise(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                yield {"_line": line_number, "_parse_error": str(exc)}
                continue
            if isinstance(record, dict):
                record["_line"] = line_number
                yield record
            else:
                yield {"_line": line_number, "_parse_error": "record is not an object"}


def distill_jsonl(
    input_path: str | Path,
    output_dir: str | Path,
    *,
    project: str = "knowledge-sdg",
    run_name: str | None = None,
    skill_name: str = "knowledge-distill",
    skill_version: str = "0.1.0",
    min_chars: int = 40,
    min_confidence: float = 0.85,
    log_to_trackio: bool = True,
) -> dict[str, Any]:
    """Filter candidate JSONL records and write auditable output files.

    Candidate records should contain ``text`` (or ``answer``), and may contain
    ``id``, ``source``, ``question`` and ``confidence``.  Records are accepted
    only when they have useful text, meet the confidence threshold, and are not
    duplicates.  Every rejection includes a machine-readable reason.
    """

    input_path = Path(input_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    run_name = run_name or f"distill-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}"

    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen: set[str] = set()
    reasons: Counter[str] = Counter()
    total = 0

    for record in _read_jsonl(input_path):
        total += 1
        line = record.get("_line")
        if "_parse_error" in record:
            reason = "invalid_json"
        else:
            text = str(record.get("text") or record.get("answer") or "").strip()
            confidence = record.get("confidence", 1.0)
            try:
                confidence = float(confidence)
            except (TypeError, ValueError):
                confidence = 0.0
            key = _normalise(text)
            if not text:
                reason = "missing_text"
            elif len(text) < min_chars:
                reason = "too_short"
            elif confidence < min_confidence:
                reason = "low_confidence"
            elif key in seen:
                reason = "duplicate"
            else:
                seen.add(key)
                item = {
                    key: value
                    for key, value in record.items()
                    if not key.startswith("_")
                }
                item.setdefault("text", text)
                item.setdefault("confidence", confidence)
                item["provenance"] = {
                    "source": item.get("source"),
                    "input_file": str(input_path),
                    "input_line": line,
                    "skill": skill_name,
                    "skill_version": skill_version,
                }
                accepted.append(item)
                continue
        reasons[reason] += 1
        rejected.append({**record, "rejection_reason": reason})

    metrics = {
        "input_records": total,
        "accepted_records": len(accepted),
        "rejected_records": len(rejected),
        "acceptance_rate": len(accepted) / total if total else 0.0,
        "duplicate_rate": reasons["duplicate"] / total if total else 0.0,
        "invalid_records": reasons["invalid_json"],
        "low_confidence_records": reasons["low_confidence"],
    }
    skill_hash = hashlib.sha256(
        f"{skill_name}:{skill_version}:{min_chars}:{min_confidence}".encode()
    ).hexdigest()
    manifest = {
        "project": project,
        "run": run_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input": str(input_path),
        "skill": {"name": skill_name, "version": skill_version, "hash": skill_hash},
        "rules": {"min_chars": min_chars, "min_confidence": min_confidence},
        "metrics": metrics,
        "rejection_reasons": dict(reasons),
    }

    def write_jsonl(name: str, rows: list[dict[str, Any]]) -> None:
        with (output_dir / name).open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    write_jsonl("distilled.jsonl", accepted)
    write_jsonl("rejected.jsonl", rejected)
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    if log_to_trackio:
        trackio.init(
            project=project,
            name=run_name,
            group="knowledge-distill",
            config={"skill": manifest["skill"], "rules": manifest["rules"], "input": str(input_path)},
        )
        trackio.log(metrics)
        trackio.finish()
    return manifest
