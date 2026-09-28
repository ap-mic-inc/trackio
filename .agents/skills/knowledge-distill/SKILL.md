---
name: knowledge-distill
description: Filter, structure, and audit knowledge data distillation jobs with Trackio.
---

# Knowledge data distillation

Use this skill when a coding agent turns source documents or model-generated
candidate records into a curated knowledge dataset.

The agent must preserve source attribution, use deterministic acceptance rules,
and write rejected records with a machine-readable reason. It must never invent
facts that are absent from the source. Records with uncertain support go to a
review queue rather than being silently accepted.

Candidate JSONL records use `text` or `answer`, with optional `id`, `question`,
`source`, and `confidence`. Run the validator from the repository root:

```python
from trackio.knowledge_distill import distill_jsonl

manifest = distill_jsonl("candidates.jsonl", "distill-output")
```

The output directory contains `distilled.jsonl`, `rejected.jsonl`, and
`manifest.json`. The manifest records the input, skill version, rules, counts,
and rejection reasons. Trackio logs the same counts under the
`knowledge-sdg` project, grouped as `knowledge-distill`.

Before accepting a new skill version, compare its Trackio runs and inspect the
rejection reasons. Keep the input revision and skill hash with every exported
dataset.

