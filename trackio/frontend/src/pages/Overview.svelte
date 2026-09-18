<script>
  import PageHeader from "../components/PageHeader.svelte";
  import LoadingTrackio from "../components/LoadingTrackio.svelte";
  import { getProjectSummary, getLogsBatch } from "../lib/api.js";
  import { buildColorMap } from "../lib/stores.js";
  import { openRunDetail } from "../lib/router.js";
  import { getAppPollIntervalMs, isTabHidden } from "../lib/hostPolling.js";

  let { project = null, runs = [] } = $props();

  const LIVE_THRESHOLD_S = 120;
  const IDLE_THRESHOLD_S = 600;
  const HEADLINE_PATTERN = /(^|[/_.])(loss|reward|return|score|accuracy|acc)([/_.]|$)/i;
  const CHIP_LIMIT = 12;

  const TAIL_ROWS = 50;
  const MAX_POINTS = 400;

  let statusRuns = $state(null);
  let loading = $state(true);
  let nowMs = $state(Date.now());
  let expandedRuns = $state({});
  let loadSeq = 0;

  let runColorMap = $derived(buildColorMap(runs));

  function isNumeric(v) {
    return typeof v === "number" && isFinite(v);
  }

  function buildStatus(record, logs) {
    const metricValues = {};
    for (let i = logs.length - 1; i >= 0; i--) {
      const row = logs[i];
      for (const [key, value] of Object.entries(row)) {
        if (key === "timestamp" || key === "step" || !isNumeric(value)) continue;
        const entry = metricValues[key];
        if (!entry) {
          metricValues[key] = {
            last: value,
            prev: null,
            step: row.step,
            timestamp: row.timestamp,
          };
        } else if (entry.prev == null) {
          entry.prev = value;
        }
      }
    }
    const last = logs.length ? logs[logs.length - 1] : null;
    const tail = logs.slice(-TAIL_ROWS);
    return {
      id: record.id,
      name: record.name,
      first_timestamp: record.created_at ?? (logs.length ? logs[0].timestamp : null),
      last_timestamp: last ? last.timestamp : null,
      last_step: last ? last.step : null,
      tail_first_timestamp: tail.length ? tail[0].timestamp : null,
      tail_first_step: tail.length ? tail[0].step : null,
      metrics: metricValues,
    };
  }

  async function load() {
    const seq = ++loadSeq;
    if (!project) {
      statusRuns = [];
      loading = false;
      return;
    }
    try {
      const summary = await getProjectSummary(project);
      const records = summary?.runs || [];
      if (seq !== loadSeq) return;
      if (!records.length) {
        statusRuns = [];
        return;
      }
      const batch = await getLogsBatch(
        project,
        records.map((r) => ({ name: r.name, id: r.id })),
        { max_points: MAX_POINTS },
      );
      if (seq !== loadSeq) return;
      statusRuns = records.map((rec, i) => buildStatus(rec, batch[i]?.logs || []));
    } catch (e) {
      if (seq === loadSeq) console.error("Failed to load run status:", e);
    } finally {
      if (seq === loadSeq) loading = false;
    }
  }

  $effect(() => {
    project;
    statusRuns = null;
    loading = true;
    load();
    const poll = setInterval(() => {
      if (!isTabHidden()) load();
    }, getAppPollIntervalMs());
    const tick = setInterval(() => {
      nowMs = Date.now();
    }, 1000);
    return () => {
      clearInterval(poll);
      clearInterval(tick);
    };
  });

  function ageSeconds(iso) {
    if (!iso) return null;
    return Math.max(0, (nowMs - new Date(iso).getTime()) / 1000);
  }

  function runState(run) {
    const age = ageSeconds(run.last_timestamp);
    if (age == null) return "unknown";
    if (age < LIVE_THRESHOLD_S) return "training";
    if (age < IDLE_THRESHOLD_S) return "idle";
    return "stopped";
  }

  const STATE_LABELS = {
    training: "training",
    idle: "idle",
    stopped: "no recent logs",
    unknown: "unknown",
  };

  function fmtAgo(seconds) {
    if (seconds == null) return "—";
    if (seconds < 10) return "just now";
    if (seconds < 60) return `${Math.floor(seconds)}s ago`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m ago`;
    return `${Math.floor(seconds / 86400)}d ${Math.floor((seconds % 86400) / 3600)}h ago`;
  }

  function fmtDuration(seconds) {
    if (seconds == null || !isFinite(seconds)) return "—";
    seconds = Math.max(0, seconds);
    if (seconds < 60) return `${Math.floor(seconds)}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
    return `${Math.floor(seconds / 86400)}d ${Math.floor((seconds % 86400) / 3600)}h`;
  }

  function fmtValue(v) {
    if (v == null || !isFinite(v)) return "—";
    if (v === 0) return "0";
    const abs = Math.abs(v);
    if (Number.isInteger(v) && abs < 1e9) return v.toLocaleString("en-US");
    if (abs >= 1e6 || abs < 1e-3) return v.toExponential(3);
    if (abs >= 1000) return v.toLocaleString("en-US", { maximumFractionDigits: 1 });
    return v.toPrecision(4).replace(/\.?0+$/, "");
  }

  function fmtInt(v) {
    if (v == null) return "—";
    return Number(v).toLocaleString("en-US");
  }

  const LOWER_IS_BETTER = /(^|[/_.])(loss|error|err|perplexity|ppl|kl)([/_.]|$)/i;
  const NEUTRAL_METRICS = /(^|[/_.])(lr|learning_rate|epoch|steps?|tokens?|samples?|batch|temperature)([/_.]|$)/i;

  function delta(entry, name) {
    if (!entry || entry.prev == null || entry.last == null) return null;
    const d = entry.last - entry.prev;
    if (d === 0) return { dir: "flat", text: "0", tone: "neutral" };
    const dir = d > 0 ? "up" : "down";
    let tone = "neutral";
    if (!NEUTRAL_METRICS.test(name || "")) {
      const improving = LOWER_IS_BETTER.test(name || "") ? dir === "down" : dir === "up";
      tone = improving ? "good" : "bad";
    }
    return { dir, text: fmtValue(Math.abs(d)), tone };
  }

  function headlineMetric(run) {
    const names = Object.keys(run.metrics || {});
    if (!names.length) return null;
    const preferred = names.filter((n) => HEADLINE_PATTERN.test(n)).sort((a, b) => a.length - b.length);
    const name = preferred[0] || names.sort()[0];
    return { name, ...run.metrics[name] };
  }

  function otherMetrics(run) {
    const head = headlineMetric(run);
    return Object.keys(run.metrics || {})
      .filter((n) => !head || n !== head.name)
      .sort()
      .map((n) => ({ name: n, ...run.metrics[n] }));
  }

  function stepsPerMin(run) {
    if (
      run.tail_first_timestamp == null ||
      run.last_timestamp == null ||
      run.tail_first_step == null ||
      run.last_step == null
    )
      return null;
    const dt = (new Date(run.last_timestamp).getTime() - new Date(run.tail_first_timestamp).getTime()) / 1000;
    const ds = run.last_step - run.tail_first_step;
    if (dt <= 0 || ds <= 0) return null;
    return (ds / dt) * 60;
  }

  function runKey(run) {
    return run.id ?? run.name;
  }

  function toggleExpanded(run) {
    const key = runKey(run);
    expandedRuns = { ...expandedRuns, [key]: !expandedRuns[key] };
  }

  let orderedRuns = $derived.by(() => {
    if (!statusRuns) return [];
    return [...statusRuns].sort(
      (a, b) => new Date(b.last_timestamp || 0) - new Date(a.last_timestamp || 0),
    );
  });

  let liveCount = $derived(orderedRuns.filter((r) => runState(r) === "training").length);
</script>

<div class="overview-page workspace-page">
  <PageHeader
    title="Overview"
    description="Live training status at a glance: current step, last update, and the latest metric values for every run."
    count={statusRuns ? statusRuns.length : null}
  />
  {#if loading && statusRuns == null}
    <LoadingTrackio />
  {:else if !orderedRuns.length}
    <div class="empty-state">
      <h2>No runs in this project</h2>
      <p>Runs appear here as soon as you call <code>trackio.init()</code> and log a step:</p>
      <pre><code>{'import trackio\ntrackio.init(project="my-project")\nfor i in range(10):\n    trackio.log({"loss": 1 / (i + 1)})\ntrackio.finish()'}</code></pre>
    </div>
  {:else}
    {#if liveCount > 0}
      <div class="live-summary">
        <span class="pulse-dot"></span>
        {liveCount} run{liveCount === 1 ? "" : "s"} receiving logs right now
      </div>
    {/if}
    <div class="status-list">
      {#each orderedRuns as run (runKey(run))}
        {@const state = runState(run)}
        {@const head = headlineMetric(run)}
        {@const headDelta = head ? delta(head, head.name) : null}
        {@const rate = stepsPerMin(run)}
        {@const others = otherMetrics(run)}
        {@const expanded = !!expandedRuns[runKey(run)]}
        <article class="status-card" class:live={state === "training"}>
          <div class="status-line">
            <div class="status-name">
              <span class="run-dot" style:background={runColorMap[runKey(run)] ?? "#9ca3af"}></span>
              <button class="run-link" onclick={() => openRunDetail(run.name, run.id)}>{run.name}</button>
              <span class="state-badge state-{state}">
                {#if state === "training"}<span class="pulse-dot"></span>{/if}
                {STATE_LABELS[state]}
              </span>
            </div>
            <div class="clock-col">
              <span class="clock-main">updated {fmtAgo(ageSeconds(run.last_timestamp))}</span>
              <span class="clock-sub">
                started {fmtAgo(ageSeconds(run.first_timestamp))}
                · ran {fmtDuration(
                  (new Date(run.last_timestamp).getTime() - new Date(run.first_timestamp).getTime()) / 1000,
                )}
              </span>
            </div>
            <div class="big-step">
              <span class="big-step-label">step</span>
              <span class="big-step-value">{fmtInt(run.last_step)}</span>
            </div>
          </div>
          <div class="kv">
            {#if head}
              <div class="kv-cell">
                <div class="k" title={head.name}>{head.name}</div>
                <div class="v">
                  {fmtValue(head.last)}
                  {#if headDelta && headDelta.dir !== "flat"}
                    <span class="delta {headDelta.tone}">{headDelta.dir === "up" ? "▲" : "▼"}{headDelta.text}</span>
                  {/if}
                </div>
              </div>
            {/if}
            {#if rate != null}
              <div class="kv-cell">
                <div class="k">throughput</div>
                <div class="v">
                  {rate >= 10 ? rate.toFixed(0) : rate.toFixed(1)}<span class="u">steps/min</span>
                </div>
              </div>
            {/if}
            <div class="kv-cell">
              <div class="k">metrics</div>
              <div class="v">{fmtInt(Object.keys(run.metrics || {}).length)}</div>
            </div>
          </div>
          {#if others.length}
            <div class="chips">
              {#each expanded ? others : others.slice(0, CHIP_LIMIT) as m (m.name)}
                {@const d = delta(m, m.name)}
                <div class="chip" title="{m.name} · step {m.step}">
                  <span class="chip-name">{m.name}</span>
                  <span class="chip-value">{fmtValue(m.last)}</span>
                  {#if d && d.dir !== "flat"}
                    <span class="delta {d.tone}">{d.dir === "up" ? "▲" : "▼"}{d.text}</span>
                  {/if}
                </div>
              {/each}
              {#if others.length > CHIP_LIMIT}
                <button class="chip chip-more" onclick={() => toggleExpanded(run)}>
                  {expanded ? "show less" : `+${others.length - CHIP_LIMIT} more`}
                </button>
              {/if}
            </div>
          {/if}
        </article>
      {/each}
    </div>
  {/if}
</div>

<style>
  .overview-page {
    min-width: 0;
    box-sizing: border-box;
    padding: 28px;
    overflow-y: auto;
    flex: 1;
  }
  .live-summary {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 16px;
    padding: 6px 12px;
    border: 1px solid var(--border-color-primary, #e5e7eb);
    border-radius: 999px;
    background: var(--background-fill-secondary, #f9fafb);
    color: var(--body-text-color, #1f2937);
    font-size: 13px;
  }
  .status-list {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }
  .status-card {
    border: 1px solid var(--border-color-primary, #e5e7eb);
    border-radius: 12px;
    padding: 18px 20px;
    background: var(--background-fill-primary, #fff);
  }
  .status-card.live {
    border-color: color-mix(in srgb, #10b981 45%, var(--border-color-primary, #e5e7eb));
  }
  .status-line {
    display: flex;
    align-items: center;
    gap: 24px;
    flex-wrap: wrap;
  }
  .status-name {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
    flex: 1 1 220px;
  }
  .run-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .run-link {
    background: none;
    border: none;
    padding: 0;
    font: inherit;
    font-weight: 600;
    font-size: 15px;
    color: var(--body-text-color, #1f2937);
    cursor: pointer;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .run-link:hover {
    color: var(--color-accent, #f97316);
    text-decoration: underline;
  }
  .state-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 2px 9px;
    border-radius: 999px;
    font-size: 11.5px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    white-space: nowrap;
  }
  .state-training {
    color: #047857;
    background: rgba(16, 185, 129, 0.12);
  }
  .state-idle {
    color: #b45309;
    background: rgba(245, 158, 11, 0.14);
  }
  .state-stopped,
  .state-unknown {
    color: var(--body-text-color-subdued, #6b7280);
    background: var(--background-fill-secondary, #f3f4f6);
  }
  .pulse-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #10b981;
    animation: pulse 1.6s ease-in-out infinite;
    flex-shrink: 0;
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.5); }
    50% { opacity: 0.6; box-shadow: 0 0 0 4px rgba(16, 185, 129, 0); }
  }
  .big-step {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 3px;
    white-space: nowrap;
    padding-left: 20px;
    border-left: 1px solid var(--border-color-primary, #e5e7eb);
  }
  .big-step-label {
    font-size: 10.5px;
    color: var(--body-text-color-subdued, #6b7280);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    line-height: 1;
  }
  .big-step-value {
    font-size: 22px;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    color: var(--body-text-color, #1f2937);
    line-height: 1;
  }
  .clock-col {
    display: flex;
    flex-direction: column;
    gap: 2px;
    margin-left: auto;
    text-align: right;
    white-space: nowrap;
  }
  .clock-main {
    font-size: 13px;
    font-weight: 500;
    color: var(--body-text-color, #1f2937);
    font-variant-numeric: tabular-nums;
  }
  .clock-sub {
    font-size: 11.5px;
    color: var(--body-text-color-subdued, #6b7280);
    font-variant-numeric: tabular-nums;
  }
  .kv {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(160px, 240px));
    gap: 10px;
    margin-top: 16px;
  }
  .kv-cell {
    border-radius: var(--radius-lg, 8px);
    padding: 10px 12px;
    background: var(--background-fill-secondary, #f9fafb);
    min-width: 0;
  }
  .kv-cell .k {
    font-size: 11px;
    color: var(--body-text-color-subdued, #6b7280);
    text-transform: uppercase;
    letter-spacing: 0.04em;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .kv-cell .v {
    margin-top: 3px;
    font-size: 17px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    color: var(--body-text-color, #1f2937);
  }
  .kv-cell .u {
    margin-left: 4px;
    font-size: 11px;
    font-weight: 400;
    color: var(--body-text-color-subdued, #6b7280);
  }
  .delta {
    margin-left: 6px;
    font-size: 12px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }
  .delta.good { color: #059669; }
  .delta.bad { color: #dc2626; }
  .delta.neutral { color: var(--body-text-color-subdued, #6b7280); }
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 14px;
  }
  .chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    max-width: 100%;
    padding: 3px 10px;
    border: 1px solid var(--border-color-primary, #e5e7eb);
    border-radius: 999px;
    background: var(--background-fill-primary, #fff);
    font-size: 12px;
  }
  .chip-name {
    color: var(--body-text-color-subdued, #6b7280);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 220px;
  }
  .chip-value {
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    color: var(--body-text-color, #1f2937);
  }
  .chip-more {
    cursor: pointer;
    font: inherit;
    font-size: 12px;
    color: var(--color-accent, #f97316);
    background: none;
  }
  .chip-more:hover { text-decoration: underline; }
  .empty-state {
    border: 1px dashed var(--border-color-primary, #e5e7eb);
    border-radius: 12px;
    padding: 32px;
    color: var(--body-text-color-subdued, #6b7280);
  }
  .empty-state h2 {
    color: var(--body-text-color, #1f2937);
    font-size: 16px;
    margin-bottom: 8px;
  }
  .empty-state pre {
    margin-top: 12px;
    padding: 12px;
    border-radius: 8px;
    background: var(--background-fill-secondary, #f9fafb);
    overflow-x: auto;
    font-size: 12.5px;
  }
  @media (max-width: 700px) {
    .overview-page { padding: 20px 16px; }
    .clock-col { margin-left: 0; text-align: left; }
    .big-step { padding-left: 0; border-left: none; align-items: flex-start; }
  }
</style>
