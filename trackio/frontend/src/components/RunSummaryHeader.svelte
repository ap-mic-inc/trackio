<script>
  import { getRunSummary } from "../lib/api.js";

  let { project = null, run = null, config = null } = $props();
  let summary = $state(null);
  let loading = $state(false);
  let failed = $state(false);
  let loadSeq = 0;

  $effect(() => {
    const selectedProject = project;
    const selectedRun = run;
    const seq = ++loadSeq;

    summary = null;
    failed = false;
    if (!selectedProject || !selectedRun) {
      loading = false;
      return;
    }

    loading = true;
    const runRef = selectedRun.id != null
      ? { id: selectedRun.id, name: selectedRun.name }
      : selectedRun.name;
    getRunSummary(selectedProject, runRef)
      .then((result) => {
        if (seq === loadSeq) summary = result;
      })
      .catch(() => {
        if (seq === loadSeq) failed = true;
      })
      .finally(() => {
        if (seq === loadSeq) loading = false;
      });

    return () => {
      if (loadSeq === seq) loadSeq++;
    };
  });
</script>

<section class="run-summary-card" aria-label="Selected run information">
  {#if loading}
    <p class="run-summary-loading">Loading run information…</p>
  {:else if summary}
    <h2>{summary.run || run.name}</h2>
    <div class="run-summary-grid">
      <div class="run-summary-item">
        <span>Project</span>
        <strong>{summary.project || project}</strong>
      </div>
      <div class="run-summary-item">
        <span>Total Logs</span>
        <strong>{summary.num_logs ?? 0}</strong>
      </div>
      <div class="run-summary-item">
        <span>Last Step</span>
        <strong>{summary.last_step ?? "N/A"}</strong>
      </div>
      <div class="run-summary-item metrics-item">
        <span>Metrics</span>
        <strong>{summary.metrics?.length ? summary.metrics.join(", ") : "N/A"}</strong>
      </div>
    </div>
    <div class="run-summary-config">
      <h3>Configuration</h3>
      {#if summary.config != null || config != null}
        <pre>{JSON.stringify(summary.config ?? config, null, 2)}</pre>
      {:else}
        <p>No configuration logged.</p>
      {/if}
    </div>
  {:else if failed}
    <p class="run-summary-loading">Could not load information for {run.name}.</p>
  {/if}
</section>

<style>
  .run-summary-card { margin: 0 0 22px; padding: 18px 20px; border: 1px solid var(--border-color-primary); border-radius: var(--radius-xl); background: var(--background-fill-primary); box-shadow: var(--shadow-drop); }
  .run-summary-card h2 { margin: 0 0 16px; color: var(--body-text-color); font-size: 17px; font-weight: 600; overflow-wrap: anywhere; }
  .run-summary-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px 20px; }
  .run-summary-item { display: flex; flex-direction: column; gap: 5px; min-width: 0; }
  .run-summary-item span, .run-summary-config h3 { color: var(--body-text-color-subdued); font-size: 11px; font-weight: 500; }
  .run-summary-item strong { color: var(--body-text-color); font-size: 13px; font-weight: 500; overflow-wrap: anywhere; }
  .metrics-item { grid-column: 1 / -1; }
  .run-summary-config { margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--border-color-primary); }
  .run-summary-config h3 { margin: 0 0 8px; }
  .run-summary-config pre { margin: 0; padding: 12px; border-radius: var(--radius-md); background: var(--background-fill-secondary); color: var(--body-text-color); font-size: 12px; line-height: 1.5; white-space: pre-wrap; overflow-wrap: anywhere; }
  .run-summary-config p, .run-summary-loading { margin: 0; color: var(--body-text-color-subdued); font-size: 12px; }
  @media (max-width: 700px) { .run-summary-card { padding: 15px; } .run-summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
