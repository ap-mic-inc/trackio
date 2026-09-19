# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Code Style

- AVOID inline comments in code!!!
- Don't create a .changeset file manually in the PR. Once you create a PR, a GH action will create it automatically based on the PR title

## Commands

### Development Setup
```bash
# Install with development dependencies
pip install -e .[dev,tensorboard]
```

### Running Tests
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_run.py

# Run e2e tests
pytest tests/e2e/
```

### Code Formatting and Linting
```bash
# Format and lint code (required before commits)
ruff check --fix --select I && ruff format
```

### Running the Application
```bash
# Launch dashboard for all projects
trackio show

# Launch dashboard for specific project
trackio show --project "project_name"
```

## Architecture Overview

Trackio is a lightweight experiment tracking library that provides a drop-in replacement for Weights & Biases (wandb). The architecture follows a clean separation between the API layer, UI layer, and storage layer.

### Core Flow
1. **User API** (`trackio/__init__.py`, `run.py`) - Provides wandb-compatible API (`init()`, `log()`, `finish()`)
2. **Storage Layer** (`sqlite_storage.py`) - Manages SQLite database operations for local persistence
3. **API Layer** (`ui/main.py`) - Gradio-based API server exposing endpoints via `gr.api()`
4. **Frontend** (`frontend/`) - Svelte 5 SPA dashboard served alongside the Gradio API
5. **Background Sync** (`commit_scheduler.py`) - Optional Hugging Face dataset synchronization

### Key Design Decisions

**Local-First Architecture**: All data is stored locally in SQLite databases at `~/.cache/huggingface/trackio/`. The system works completely offline by default.

**Queued Logging**: The `Run` class uses a queue-based system for logging to handle concurrent access safely. Background clients process log entries asynchronously.

**Cloud Integration**: Optional deployment to Hugging Face Spaces uses the `deploy.py` module. When deployed, data syncs to HF Datasets every 5 minutes via `CommitScheduler`.

**Context Management**: Uses Python context variables (`context_vars.py`) to track the current run across function calls, similar to wandb's approach.

### Testing Strategy

Tests are split into unit tests (testing individual modules) and e2e tests (testing complete workflows). The `conftest.py` provides fixtures for temporary databases and test isolation. Always run tests before committing changes.

### Important Files for Common Tasks

- **Adding new logging features**: Modify `run.py` (Run class) and `sqlite_storage.py` (storage operations)
- **Changing UI/dashboard**: Edit `frontend/src/` (Svelte 5 components), then run `npm run build` in `trackio/frontend/`
- **Changing API endpoints**: Edit `ui/main.py` (Gradio API layer)
- **Modifying API compatibility**: Update `trackio/__init__.py` and ensure wandb compatibility
- **Adding import formats**: Extend `imports.py` with new import functions
- **CLI modifications**: Update `cli.py` and entry points in `pyproject.toml`

## Dashboard Frontend Reference (for AI-assisted development)

### Commands

```bash
cd trackio/frontend
npm ci          # once; the root pnpm install does not cover the frontend
npm test        # vitest; unit tests live in src/lib/*.test.js
npm run lint
npm run build   # required after edits: `trackio show` serves dist/, not sources
```

### Visual verification loop

Never ship a styling or layout change without looking at it. Seed demo data
into an isolated directory, launch the server, and screenshot with Playwright
(the repo `.venv` has Python Playwright installed):

```bash
TRACKIO_DIR=/tmp/trackio-demo python seed_demo.py   # trackio.init/log/finish
TRACKIO_DIR=/tmp/trackio-demo GRADIO_SERVER_PORT=7860 trackio show
```

Check both themes: append `?__theme=dark` to any dashboard URL.

### Design conventions

- Style exclusively with the CSS variables from
  `frontend/src/lib/gradio-theme.css`; dark mode overrides them in
  `frontend/src/lib/theme.js`. Never hardcode colors.
- The `--neutral-*` scale is NOT inverted in dark mode. Derive hover and
  border tints from semantic vars or `color-mix()`, never from `--neutral-*`.
- Radius tokens: `--radius-md` 6px, `--radius-lg` 8px, `--radius-xl` 10px,
  `--radius-xxl` 14px. Cards are a single border layer plus `--shadow-drop`;
  accent CTAs use `--primary-600`.
- Shared components: `PageHeader.svelte` (page titles), `CodeSnippet.svelte`
  (copyable code blocks; bind the real project name so snippets run as
  pasted), `Accordion.svelte` (flat group headings, not boxed cards), and
  `lib/workspace.css` (`.workspace-page`, `.empty-state`).
- Keep vega/vega-embed behind `lib/vegaLoader.js` (lazy-loaded). Static
  imports of vega put ~850 kB back into the entry chunk.

### Conventions the dashboard understands

- Metric prefixes `train/`, `eval/`, `perf/` become chart sections and the
  Metrics page's group chips.
- `trackio.init(group=...)` feeds the sidebar's Group by.
- Overview picks its headline metric by name (`loss`, `reward`, `accuracy`,
  `score`, ...), so recommend those names in examples.

### Testability pattern

Logic embedded in `.svelte` files is not unit-tested in this repo; extract
decisions into `frontend/src/lib/*.js` and cover them with vitest. Example:
`resolveXColumn` in `dataProcessing.js` keeps the metric X-axis independent
of run order and is tested in `dataProcessing.test.js`.

### Server and auth notes

- The SPA middleware in `trackio/frontend_server.py` serves `index.html` for
  everything except reserved paths. A backend endpoint that shares a prefix
  with an SPA route (like `/file` vs the `/files` page) must be reserved as
  an exact path, not a prefix. Regression tests:
  `tests/unit/test_frontend_server.py`.
- OIDC sign-in is enabled whenever an issuer URL and client ID are
  configured. Admin-page settings win; `TRACKIO_OIDC_*` env vars are the
  fallback while those fields are empty. Tests: `tests/unit/test_oidc.py`.
- For end-to-end auth checks, a fake IdP only needs
  `/.well-known/openid-configuration`, an authorize endpoint that 302s back
  with `code`+`state`, and a token endpoint returning an unsigned JWT
  `id_token` (signatures are not verified for tokens fetched directly from
  the token endpoint over the authenticated channel).

## GitHub Issue Fix Workflow

When asked to fix a GitHub issue and prepare a PR, use the following end-to-end
workflow. The goal is to give reviewers observable before/after evidence, not only a
patch and a passing unit test.

### 1. Isolate the work

1. Read the issue and comments with `gh issue view <number> --repo gradio-app/trackio --comments`.
2. Fetch `origin/main` and create a dedicated worktree under
   `../trackio-worktrees/issue-<number>` from the fetched commit.
3. Use a branch such as `issue-<number>-<short-description>`. Avoid assuming the
   `fix/...` namespace is available; this repository may have a branch literally named
   `fix`.
4. Keep reproduction programs, generated data, Space staging files, screenshots, and
   issue metadata untracked. Never commit them with the fix.

### 2. Reproduce before editing source

1. Build the smallest realistic reproduction using the exact API, input, or metric name
   from the report. Name it `demo_issue_<number>.py` when appropriate.
2. Isolate local demo data by setting `TRACKIO_DIR` to a directory inside the worktree.
   Include a known-good control metric or behavior when that makes the failure clearer.
3. For frontend work, use the frontend's own lockfile and commands:

   ```bash
   cd trackio/frontend
   npm ci
   npm run build
   ```

   The root pnpm install does not install `trackio/frontend` development dependencies.
4. Run the demo against the package in the worktree. `uv sync --extra dev` followed by
   `uv run python demo_issue_<number>.py` is a convenient isolated setup.
5. Confirm the reported failure before changing source. Inspect both sides of the data
   path when useful: verify the API/storage contains the expected values, then verify
   the browser or renderer loses or misrepresents them.
6. Prefer browser verification for UI bugs. If browser automation is unavailable, use
   the closest deterministic renderer/dataflow check, keep the live demo available for
   manual inspection, and state the limitation explicitly.
7. If the issue does not reproduce on current `origin/main`, stop without editing code
   or opening a PR. Report the demo, command, observed result, and uncertainty.

### 3. Fix the root cause and add regression coverage

1. Keep the patch scoped to the confirmed failure and follow existing Trackio patterns.
2. Add a regression test that exercises the actual boundary that failed. For frontend
   renderer bugs, test the renderer/accessor semantics rather than only a string helper.
3. Cover adjacent syntax or edge cases only when the same root cause handles them; do
   not broaden the PR into unrelated cleanup.

### 4. Verify locally

Rerun the reproduction and the narrowest relevant tests, then run the complete checks
for the changed area.

For frontend changes:

```bash
cd trackio/frontend
npm test
npm run lint
npm run build
```

For Python changes, run the relevant pytest files and Ruff checks described above. Use
`git diff --check` before committing. Record exact commands and any environment-related
limitation.

### 5. Prepare a focused draft PR

1. Confirm temporary demo and data files are still untracked with `git status --short`.
2. Stage and commit only the required source and test files.
3. Do **not** create a `.changeset` manually. The Trackio GitHub workflow creates one
   from the PR title and commits it to the branch.
4. Push the issue branch and open a draft PR against `gradio-app/trackio`.
5. Keep the PR body short and include:
   - `Fixes #<number>`
   - the root cause and fix
   - verification commands
   - the minimal demo in a fenced code block
   - a note that the demo file was not committed
6. Leave the verified local demo server running and report its URL.

### 6. Drive CI to green

1. Watch required checks with `gh pr checks <pr> --repo gradio-app/trackio --watch`.
2. Treat test, lint, build, documentation, wheel, and Trackio Spaces E2E failures as
   defects in the change until evidence shows otherwise.
3. Before fixing a suspected unrelated failure, compare recent `main` runs or reproduce
   it on a clean checkout. Rerun a likely flake once. Do not add unrelated fixes to the
   issue PR.
4. The changeset bot pushes to the PR branch. Fetch and fast-forward/rebase before any
   later push to avoid a non-fast-forward rejection.
5. The preview-wheel upload and its PR-comment step are separate. If the comment step
   fails, inspect the `PR wheel preview deploy` logs; the wheel may already be uploaded
   and its exact URL will appear in the workflow inputs.

### 7. Create before/after Spaces for reviewable UI bugs

When the behavior is visible in a Trackio dashboard and the demo is safe to make public,
deploy a comparison pair such as:

- `<namespace>/trackio-<issue>-before`
- `<namespace>/trackio-<issue>-after`

Use these rules:

1. Upload byte-identical, ordinary `app.py` files to both Spaces. The app should show the
   real behavior directly; do not build an in-page PASS/FAIL test harness.
2. The only functional difference should be `requirements.txt`:
   - before: `trackio` (latest released package)
   - after: the exact preview-wheel URL produced by the PR workflow
3. A minimal Trackio Space can log its demonstration data at startup and finish with
   `trackio.show(project=...)`. Use the Gradio Space SDK, matching Trackio's own deploy
   template.
4. Give each Space a short README that explains what to inspect, says whether it is the
   released or PR version, and links to the other Space.
5. Wait for both runtimes to reach `RUNNING`. Read back `app.py` and requirements from
   the Hub, verify the app hashes match, verify both APIs serve the same demo data, and
   confirm the visual difference in a browser whenever one is available.
6. Never upload credentials, private user data, or the local Trackio cache. If a public
   demonstration is inappropriate or impossible, explain why and skip the Spaces.
7. Add or update one PR comment containing both links and a compact before/after table.
   Keep a stable HTML marker such as `<!-- trackio-before-after-spaces -->` so reruns can
   update the comment instead of duplicating it.

### 8. Final handoff

Report the worktree, branch, untracked demo path, local demo URL, draft PR, required CI
status, both Space URLs, what reviewers should observe, and any remaining caveat. Ask
the reviewer to open both Spaces and confirm the visible difference.
