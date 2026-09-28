# Upstream main merge review

Reviewed on 2026-09-27 against the gradio-app/trackio main branch at commit d93511b (trackio 0.39.0). The local branch is feat/generic-oidc-auth, currently at dac44ca. The merge base is 0e3eb8c.

## Recommendation

Upstream can be merged, but a direct merge is not a low-risk update. Git reports 13 upstream-only commits and 18 local-only commits. A merge-tree dry run finds content conflicts in:

- trackio/frontend/src/App.svelte
- trackio/frontend/src/components/BarPlot.svelte
- trackio/frontend/src/components/HistogramPlot.svelte
- trackio/frontend/src/components/LinePlot.svelte
- trackio/frontend/src/pages/Metrics.svelte

The local run-status implementation touches server.py, sqlite_storage.py, api.js, and Overview, overlapping upstream backend and frontend work even where Git's committed-tree dry run can auto-merge. Resolve that overlap as part of integration. The worktree also contains separate untracked knowledge-distillation files that must remain intact.

## Upstream changes to consider

| Upstream change | Recommendation |
| --- | --- |
| #692 / 217a949 — fix CommitOperationAdd import for huggingface_hub 1.32 | Low-conflict compatibility fix. Bring it in after checking the supported dependency range and running the relevant sync checks. |
| #688 / e332a26 — show Trackio version under the logo | Low-risk UI improvement. Inspect the local logo, compact sidebar, and theme layout before retaining it. |
| #696 / 81ae55f — hide empty dashboard tabs on narrow screens | Useful responsive behavior, but it edits App.svelte, which already has local OIDC routes, custom navigation, and sidebar behavior. Manually combine the conditions. |
| #697 / 89c9b1b — expose and restore dashboard view state for embeds | Potentially useful for sharing Overview and Metrics views. It overlaps local URL state, App.svelte, Metrics.svelte, and the current project-lock behavior; compare state formats and preserve the current project / selected_project semantics. |
| #684 / 10011b0 — release chart canvases outside the viewport | Valuable performance work, but it conflicts directly with local chart and Metrics changes. Port the lifecycle handling and its regression coverage while retaining local plot controls and lazy loading. |
| #687 / e1a2d38 — make fragment inbox startup non-blocking and batch imports | Worth reviewing for Spaces startup reliability. It touches fragment scheduling and server behavior; check import ordering, locks, retries, and the new status endpoint together. |
| #682 / b2f160f — resolve registry locations with use_artifact | Substantial feature and storage change. Review the SQLite schema and migration path, local versus remote source behavior, bucket handling, and new resolution tests as one unit before adopting. |
| #693 / 3db5e38 — add overwrite to log_artifact | Do not adopt blindly: overwrite changes artifact lifecycle semantics. Confirm version history, alias behavior, and callers' expectations first. |
| 0.38.0–0.39.0 release metadata and version bumps | Review package versions, changelogs, and changesets separately. Upstream is at 0.39.0; this fork's package metadata may intentionally differ. Do not use a broad merge to settle release numbering. |

These upstream commits are visible in the [upstream repository](https://github.com/gradio-app/trackio) and their detailed changes are available by commit hash in the table.

## Local behavior to preserve during integration

- Generic OIDC, local account setup/login, admin controls, per-user permissions, and the current local-account default role (52f9165, 5bd3656, 0a8ec8b, 4836776, 447925b, f28c720).
- The custom dashboard structure: workspace page headers, sidebar groups, compact Runs/Overview navigation, lazy-loaded Vega, plot controls, and robust axis selection (5e46ba9, 015bbcd, 3c16415, 3790039, 57f33b3, dac44ca).
- LLM training recipes and Python Quickstart, including the recent move into tabs above the Runs list (af0a6b4 and current uncommitted edits).
- The Overview run-status endpoint, bounded metric summaries, stale-data behavior, manual refresh, and its UI work; these are currently uncommitted and overlap upstream server.py, sqlite_storage.py, and frontend APIs.
- Untracked knowledge-distillation work (trackio/knowledge_distill.py, its skill, candidate data, and patch plan). It is outside the upstream merge and should not be staged or discarded as part of it.

## Safe merge sequence

1. Save and review the current worktree, including untracked files; commit or create a recoverable patch before merging.
2. Merge upstream in a clean worktree so conflicts can be resolved without disturbing the current local edits.
3. Resolve the five dashboard conflicts by combining behavior, not choosing one side wholesale. Then reconcile the uncommitted status API changes with upstream server.py, sqlite_storage.py, and api.js.
4. Review artifact registry and overwrite changes independently, including schema compatibility and their upstream regression checks.
5. Reapply the Overview status work and Runs guide tabs, then run the backend and frontend checks before updating the feature branch.
