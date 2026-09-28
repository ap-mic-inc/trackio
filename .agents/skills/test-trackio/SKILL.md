---
name: test-trackio
description: How to test a Trackio change in this fork before committing — unit tests against the HEAD baseline, frontend checks, isolated servers and data, Playwright screenshots in both themes, and verifying staged commits on their own. Use when asked to test, verify, 測試, 驗證, or check a change, before committing, or when a test fails and you need to know whether it is new.
---

# Test a Trackio change

Work from the repository root with the repo virtualenv (`.venv/bin/python`,
`.venv/bin/trackio`; `python` may not be on PATH). For the Claude Code / Codex
integration, also run the `test-agent-traces` skill.

## 1. Python: compare against HEAD, not against "all green"

This machine has no GPU, ffmpeg, or pyarrow, so about 13 unit tests fail on a
clean checkout (`test_gpu_hardware`, video `test_media`, parquet
`test_import_export` / `test_artifact_persistence` / trace export). Do not read
those as regressions, and do not "fix" them in an unrelated change.

```bash
.agents/skills/test-trackio/scripts/unit_vs_head.sh            # all of tests/unit
.agents/skills/test-trackio/scripts/unit_vs_head.sh tests/unit/test_run.py -k resume
```

It runs the tests on an export of HEAD and on the working tree (without touching
either) and exits 1 only for failures that are new. Then:

```bash
.venv/bin/ruff check trackio tests && .venv/bin/ruff format --check trackio tests
```

Two files (`tests/unit/test_local_auth.py`, `trackio/knowledge_distill.py`) are
already unformatted on HEAD; only format files you changed.

## 2. Frontend

```bash
cd trackio/frontend && npm test && npm run lint && npm run build
```

`trackio show` serves `dist/`, so rebuild before looking at the UI. Put logic in
`src/lib/*.js` with a vitest file next to it (see `markdown.test.js`,
`alertDismiss.test.js`); `.svelte` files are not unit-tested.

## 3. Never test against the user's data

- Set `TRACKIO_DIR` to a scratch directory **before** Python imports `trackio`
  (the path is read at import time). A script that sets it afterwards writes to
  `~/.cache/huggingface/trackio`. If that happens, list what the run created
  (by timestamp) and delete only that.
- Do not add or delete runs, alerts, or projects in the user's dashboard data
  (e.g. `~/trackio-dev-data`) to test; copy it or seed a new project with the
  `seed-test-data` skill.
- Start test servers on another port with a fixed token:

  ```bash
  TRACKIO_WRITE_TOKEN=test TRACKIO_DIR=/tmp/t/server GRADIO_SERVER_PORT=7862 \
    nohup .venv/bin/trackio show > /tmp/t/server.log 2>&1 &
  ```

  Stop them when done (`ss -ltnp | grep :7862` for the pid). Without a fixed
  `TRACKIO_WRITE_TOKEN` every restart mints a new token and browsers with the
  old cookie silently lose write access (dismiss, rename, delete disappear or
  are disabled).
- In pytest, use the `temp_dir` fixture; patch `HOME`, `CLAUDE_CONFIG_DIR`, and
  `CODEX_HOME` when testing anything that writes user-level settings.

## 4. Look at the UI

```bash
.venv/bin/python .agents/skills/test-trackio/scripts/ui_check.py \
  --url http://127.0.0.1:7862 --project my-project \
  --pages overview,traces,reports --out /tmp/ui [--token TOKEN] [--selector ".report-content"]
```

It saves `<page>-<theme>.png` for light and dark, collapses the floating alert
panel, and exits 1 on console errors. Then actually read the screenshots:

- Check empty states too (a project with no traces/files/reports), and the
  read-only view (no token) as well as the write view.
- For layout claims, measure instead of eyeballing: `locator.bounding_box()`
  for widths and heights, `getComputedStyle` for styles.
- Clicking the middle of the alert header can hit a filter pill; target
  `.alert-header .collapse-icon`.
- Selectors: headings styled uppercase (e.g. "EXECUTION") have mixed-case text
  in the DOM ("Execution"); use `exact=True` role names to avoid matching the
  alert header.

## 5. Check the running server is the code you think

`trackio --version` prints `0.39.0 (<commit>[+<hash of local changes>])`; the
dashboard shows the revision it was started with under the logo, also at
`curl -s http://127.0.0.1:<port>/version`. If they differ, restart the server.
Frontend-only changes are served from `dist/` without a restart.

## 6. Verify each commit on its own

When splitting work into commits, check that the staged index works without the
rest of the working tree:

```bash
.agents/skills/test-trackio/scripts/verify_staged.sh [--frontend] tests/unit/test_x.py
```

It exports the index to a temporary directory and runs ruff, an import check,
the given tests, and (with `--frontend`) eslint, vite build, and vitest there.
`git add -p` is not available non-interactively; stage partial files by
building the intended file content and writing it with
`git hash-object -w --stdin` + `git update-index --cacheinfo`.

Commit messages follow `type(scope): summary` and end with the Co-Authored-By
line; no inline code comments (see CLAUDE.md).
