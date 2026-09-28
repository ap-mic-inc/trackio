<script>
  import PageHeader from "../components/PageHeader.svelte";
  import Quickstart from "../components/Quickstart.svelte";
  import { reportsGuide } from "../lib/quickstarts.js";
  import LoadingTrackio from "../components/LoadingTrackio.svelte";
  import { getAlerts, getLogs } from "../lib/api.js";
  import { renderMarkdown } from "../lib/markdown.js";

  let { project = null, selectedRuns = [] } = $props();

  let allAlerts = $state([]);
  let markdownReports = $state([]);
  let filterLevel = $state(null);
  let loading = $state(false);

  const BADGES = { info: "🔵", warn: "🟡", error: "🔴" };

  let alerts = $derived.by(() => {
    if (!filterLevel) return allAlerts;
    return allAlerts.filter((a) => a.level === filterLevel);
  });

  async function loadData() {
    if (!project) {
      allAlerts = [];
      markdownReports = [];
      return;
    }

    loading = true;
    try {
      const data = await getAlerts(project, null, null, null);
      const selectedRunNames = new Set(selectedRuns.map((run) => run.name));
      allAlerts = (data || []).filter(
        (alert) => !alert.run || selectedRunNames.has(alert.run),
      );

      const runsToLoad = selectedRuns;
      const reports = [];
      for (const run of runsToLoad) {
        try {
          const logs = await getLogs(project, run);
          if (logs) {
            for (const log of logs) {
              for (const [key, value] of Object.entries(log)) {
                if (value && typeof value === "object" && value._type === "trackio.markdown") {
                  reports.push({
                    key,
                    run: run.name,
                    step: log.step,
                    content: value._value || "",
                  });
                }
              }
            }
          }
        } catch {
          // skip
        }
      }
      markdownReports = reports;
    } catch (e) {
      console.error("Failed to load alerts:", e);
      allAlerts = [];
    } finally {
      loading = false;
    }
  }

  $effect(() => {
    project;
    selectedRuns;
    loadData();
  });

  function formatTimestamp(ts) {
    if (!ts) return "";
    try {
      const d = new Date(ts);
      return d.toLocaleString();
    } catch {
      return ts;
    }
  }

  let tableHeaders = ["Level", "Run", "Title", "Text", "Step", "Time", "Dismissed"];
  let tableRows = $derived(
    alerts.map(a => [
      `${BADGES[a.level] || ""} ${a.level}`,
      a.run || "",
      a.title,
      a.text || "",
      a.step ?? "",
      formatTimestamp(a.timestamp),
      a.dismissed_at ? formatTimestamp(a.dismissed_at) : "",
    ])
  );
</script>

<div class="reports-page workspace-page">
  <PageHeader title="Alerts & Reports" description="Review training alerts and reports from your selected runs." />
  {#if project}
    <Quickstart guide={reportsGuide(project)} collapsible={true} />
  {/if}
  {#if loading}
    <LoadingTrackio />
  {:else if allAlerts.length === 0 && markdownReports.length === 0}
    <div class="empty-state">
      <h2>No alerts or reports yet</h2>
      <p>
        Alerts are recorded when your training script calls <code>trackio.alert()</code>.
        Reports are logged as Markdown via <code>trackio.log()</code>.
      </p>
      <pre><code>{'import trackio\nfrom trackio import AlertLevel\n\ntrackio.init(project="my-project")\ntrackio.alert("Low validation loss", text="Consider saving a checkpoint.", level=AlertLevel.INFO)\ntrackio.log({"reports/summary": trackio.Markdown("# My Report\\nResults look good.")})'}</code></pre>
    </div>
  {:else}
    {#if markdownReports.length > 0}
      <section class="reports-section">
        <h3 class="section-title">Reports ({markdownReports.length})</h3>
        {#each markdownReports as report}
          <div class="report-card">
            <div class="report-meta">{report.key} &middot; {report.run} &middot; step {report.step}</div>
            <div class="report-content">{@html renderMarkdown(report.content)}</div>
          </div>
        {/each}
      </section>
    {/if}

    {#if allAlerts.length > 0}
      <section class="alerts-section">
        <h3 class="section-title">Alerts ({allAlerts.length})</h3>
        <div class="controls">
          <div class="control">
            <div class="filter-pills">
              <button
                class="pill"
                class:active={filterLevel === null}
                onclick={() => (filterLevel = null)}>All</button
              >
              <button
                class="pill"
                class:active={filterLevel === "info"}
                onclick={() => (filterLevel = "info")}>Info</button
              >
              <button
                class="pill"
                class:active={filterLevel === "warn"}
                onclick={() => (filterLevel = "warn")}>Warn</button
              >
              <button
                class="pill"
                class:active={filterLevel === "error"}
                onclick={() => (filterLevel = "error")}>Error</button
              >
            </div>
          </div>
        </div>

        {#if alerts.length === 0}
          <p class="filter-empty">No alerts for this level.</p>
        {:else}
          <table class="alerts-table">
            <thead>
              <tr>
                {#each tableHeaders as header}
                  <th>{header}</th>
                {/each}
              </tr>
            </thead>
            <tbody>
              {#each tableRows as row, i}
                <tr class:dismissed={alerts[i].dismissed_at}>
                  {#each row as cell}
                    <td>{cell}</td>
                  {/each}
                </tr>
              {/each}
            </tbody>
          </table>
        {/if}
      </section>
    {/if}
  {/if}
</div>

<style>
  .reports-page {
    min-width: 0;
    box-sizing: border-box;
    padding: 28px;
    overflow-y: auto;
    flex: 1;
  }
  .controls {
    display: flex;
    gap: 16px;
    margin-bottom: 16px;
    flex-wrap: wrap;
    align-items: flex-end;
  }
  .control {
    min-width: 200px;
  }
  .filter-pills {
    flex-wrap: wrap;
    display: flex;
    gap: 4px;
  }
  .pill {
    border: 1px solid var(--border-color-primary, #e5e7eb);
    border-radius: var(--radius-xxl, 22px);
    padding: 4px 12px;
    font-size: var(--text-sm, 12px);
    background: var(--background-fill-secondary, #f9fafb);
    color: var(--body-text-color-subdued, #6b7280);
    cursor: pointer;
    transition: background-color 0.15s, color 0.15s;
  }
  .pill:hover {
    background: var(--background-fill-secondary, #f3f4f6);
  }
  .pill.active {
    background: var(--color-accent, #f97316);
    color: white;
    border-color: var(--color-accent, #f97316);
  }
  .alerts-table {
    width: 100%;
    border-collapse: collapse;
    font-size: var(--text-md, 14px);
  }
  .alerts-table th {
    text-align: left;
    padding: 8px 12px;
    border-bottom: 2px solid var(--border-color-primary, #e5e7eb);
    color: var(--body-text-color-subdued, #6b7280);
    font-weight: 600;
    font-size: var(--text-sm, 12px);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .alerts-table td {
    padding: 8px 12px;
    border-bottom: 1px solid var(--border-color-primary, #e5e7eb);
    color: var(--body-text-color, #1f2937);
  }
  .alerts-table tbody tr:nth-child(odd) {
    background: var(--table-odd-background-fill, var(--background-fill-primary, white));
  }
  .alerts-table tbody tr:nth-child(even) {
    background: var(--table-even-background-fill, var(--background-fill-secondary, #f9fafb));
  }
  .alerts-table tr.dismissed td {
    color: var(--body-text-color-subdued, #9ca3af);
  }
  .alerts-table tr:hover {
    background: var(--background-fill-secondary, #f3f4f6);
  }
  .section-title {
    font-size: 16px;
    font-weight: 700;
    margin: 0 0 12px;
    color: var(--body-text-color, #1f2937);
  }
  .reports-section {
    margin-bottom: 32px;
  }
  .alerts-section {
    margin-bottom: 32px;
  }
  .report-card {
    border: 1px solid var(--border-color-primary, #e5e7eb);
    border-radius: var(--radius-lg, 8px);
    padding: 16px 20px;
    margin-bottom: 12px;
    background: var(--background-fill-primary, white);
  }
  .report-meta {
    font-size: var(--text-sm, 12px);
    color: var(--body-text-color-subdued, #6b7280);
    margin-bottom: 8px;
  }
  .report-content {
    font-size: var(--text-md, 14px);
    color: var(--body-text-color, #1f2937);
    line-height: 1.6;
  }
  .report-content :global(h2) {
    font-size: 18px;
    font-weight: 700;
    margin: 0 0 8px;
  }
  .report-content :global(h3) {
    font-size: 16px;
    font-weight: 600;
    margin: 12px 0 6px;
  }
  .report-content :global(h4) {
    font-size: 14px;
    font-weight: 600;
    margin: 10px 0 4px;
  }
  .report-content :global(code) {
    background: var(--background-fill-secondary, #f0f0f0);
    padding: 1px 5px;
    border-radius: var(--radius-sm, 4px);
    font-size: 13px;
  }
  .report-content :global(h5),
  .report-content :global(h6) {
    font-size: 13px;
    font-weight: 600;
    margin: 8px 0 4px;
  }
  .report-content :global(ul),
  .report-content :global(ol) {
    margin: 4px 0;
    padding-left: 20px;
  }
  .report-content :global(a) {
    color: var(--color-accent, #f97316);
    text-decoration: underline;
  }
  .report-content :global(pre) {
    margin: 8px 0;
    padding: 10px 12px;
    overflow-x: auto;
    border: 1px solid var(--border-color-primary, #e5e7eb);
    border-radius: var(--radius-md, 6px);
    background: var(--background-fill-secondary, #f9fafb);
  }
  .report-content :global(pre code) {
    padding: 0;
    background: none;
    font-size: 12px;
  }
  .report-content :global(blockquote) {
    margin: 8px 0;
    padding: 0 12px;
    border-left: 3px solid var(--border-color-primary, #e5e7eb);
    color: var(--body-text-color-subdued, #6b7280);
  }
  .report-content :global(hr) {
    margin: 12px 0;
    border: none;
    border-top: 1px solid var(--border-color-primary, #e5e7eb);
  }
  .report-content :global(.md-table) {
    margin: 8px 0;
    overflow-x: auto;
  }
  .report-content :global(table) {
    border-collapse: collapse;
    font-size: 13px;
  }
  .report-content :global(th),
  .report-content :global(td) {
    padding: 6px 12px;
    border: 1px solid var(--border-color-primary, #e5e7eb);
    text-align: left;
  }
  .report-content :global(th) {
    background: var(--background-fill-secondary, #f9fafb);
    font-weight: 600;
  }
  .report-content :global(li) {
    margin: 2px 0;
  }
  .report-content :global(p) {
    margin: 6px 0;
  }
  .filter-empty {
    color: var(--body-text-color-subdued, #6b7280);
    font-size: var(--text-md, 14px);
  }
  @media (max-width: 700px) {
    .reports-page { padding: 20px 16px; }
  }
</style>
