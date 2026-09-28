<script>
  import PageHeader from "../components/PageHeader.svelte";
  import CodeSnippet from "../components/CodeSnippet.svelte";
  import LoadingTrackio from "../components/LoadingTrackio.svelte";
  import Quickstart from "../components/Quickstart.svelte";
  import { overviewGuide } from "../lib/quickstarts.js";
  import RunSummaryHeader from "../components/RunSummaryHeader.svelte";
  import { getRunStatus, getRunSummary } from "../lib/api.js";
  import { buildColorMap } from "../lib/stores.js";
  import { openRunDetail } from "../lib/router.js";
  import { getAppPollIntervalMs, isTabHidden, isRateLimitCooldownActive } from "../lib/hostPolling.js";
  import { createStatusLoader } from "../lib/runStatus.js";

  let {
    project = null,
    runs = [],
    runConfigs = {},
    onRunSelect = null,
  } = $props();

  const LIVE_THRESHOLD_S = 120;
  const IDLE_THRESHOLD_S = 600;
  const HEADLINE_PATTERN = /(^|[/_.])(loss|reward|return|score|accuracy|acc)([/_.]|$)/i;
  const CHIP_LIMIT = 4;

  let statusRuns = $state(null);
  let loading = $state(true);
  let manualRefreshing = $state(false);
  let failed = $state(false);
  let lastSuccess = $state(null);
  let serverOffset = $state(0);
  let snapshot = $state(false);
  let tailRows = $state(50);
  let nowMs = $state(Date.now());
  let expandedRuns = $state({});
  let detailsOpenRuns = $state({});
  let searchableSummaries = $state({});
  let searchSummaryLoading = $state(false);
  let query = $state("");
  let filter = $state("all");
  let loader = null;
  let searchSummaryCache = new Map();
  let searchSummaryToken = 0;

  let runColorMap = $derived(buildColorMap(runs));

  $effect(() => {
    const selectedProject = project;
    statusRuns = null;
    loading = true;
    manualRefreshing = false;
    failed = false;
    lastSuccess = null;
    serverOffset = 0;
    snapshot = false;
    expandedRuns = {};
    detailsOpenRuns = {};
    searchSummaryCache.clear();
    searchableSummaries = {};
    searchSummaryToken++;
    query = "";
    filter = "all";
    if (!selectedProject) {
      statusRuns = [];
      loading = false;
      return;
    }
    let isSnapshot = false;
    const current = createStatusLoader({
      request: (signal) => getRunStatus(selectedProject, { signal }),
      onSuccess: (result) => {
        statusRuns = result.runs;
        lastSuccess = Date.now();
        nowMs = lastSuccess;
        const serverTime = Date.parse(result.server_time);
        serverOffset = Number.isFinite(serverTime) ? serverTime - lastSuccess : 0;
        snapshot = isSnapshot = !!result.snapshot;
        tailRows = result.tail_rows;
        failed = false;
      },
      onError: () => { failed = true; },
      onLoading: (value) => { if (!value) loading = false; },
    });
    loader = current;
    current.load();
    const poll = setInterval(() => {
      if (!isSnapshot && !isTabHidden() && !isRateLimitCooldownActive()) current.load();
    }, getAppPollIntervalMs());
    const tick = setInterval(() => { nowMs = Date.now(); }, 1000);
    return () => {
      current.dispose();
      if (loader === current) loader = null;
      clearInterval(poll);
      clearInterval(tick);
    };
  });

  function ageSeconds(iso) {
    if (!iso) return null;
    return Math.max(0, (nowMs + serverOffset - new Date(iso).getTime()) / 1000);
  }

  async function refreshNow() {
    if (!loader || manualRefreshing) return;
    manualRefreshing = true;
    await loader.load(true);
    manualRefreshing = false;
  }

  function runState(run) {
    const age = ageSeconds(run.last_timestamp);
    if (age == null) return "unknown";
    if (snapshot) return "snapshot";
    if (age < LIVE_THRESHOLD_S) return "training";
    if (age < IDLE_THRESHOLD_S) return "idle";
    return "stopped";
  }

  const STATE_LABELS = {
    snapshot: "Snapshot",
    training: "Recent logs",
    idle: "Quiet",
    stopped: "No recent logs",
    unknown: "Awaiting logs",
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

  function toggleRunDetails(run) {
    const key = runKey(run);
    detailsOpenRuns = { ...detailsOpenRuns, [key]: !detailsOpenRuns[key] };
  }

  function configSearchText(config) {
    if (config == null) return "";
    if (Array.isArray(config)) return config.map(configSearchText).join(" ");
    if (typeof config === "object") {
      return Object.entries(config)
        .map(([key, value]) => `${key} ${configSearchText(value)}`)
        .join(" ");
    }
    return String(config);
  }

  async function loadSearchableSummaries(selectedProject, candidates, token) {
    let nextIndex = 0;
    async function worker() {
      while (nextIndex < candidates.length && token === searchSummaryToken) {
        const run = candidates[nextIndex++];
        const key = runKey(run);
        try {
          const summary = await getRunSummary(
            selectedProject,
            run.id != null ? { id: run.id, name: run.name } : run.name,
          );
          if (token !== searchSummaryToken) return;
          searchSummaryCache.set(key, summary);
          searchableSummaries = Object.fromEntries(searchSummaryCache);
        } catch {
          // Keep searching the run name, recent metrics, and loaded config.
        }
      }
    }

    await Promise.all(
      Array.from({ length: Math.min(4, candidates.length) }, () => worker()),
    );
    if (token === searchSummaryToken) searchSummaryLoading = false;
  }

  $effect(() => {
    const selectedProject = project;
    const searchTerm = query.trim();
    if (!selectedProject || !searchTerm) {
      searchSummaryLoading = false;
      return;
    }

    const candidates = runs.filter((run) => !searchSummaryCache.has(runKey(run)));
    if (!candidates.length) {
      searchSummaryLoading = false;
      return;
    }

    const token = ++searchSummaryToken;
    searchSummaryLoading = true;
    const timer = setTimeout(
      () => loadSearchableSummaries(selectedProject, candidates, token),
      250,
    );
    return () => {
      clearTimeout(timer);
      if (token === searchSummaryToken) searchSummaryToken++;
    };
  });

  function handleCardClick(e, run) {
    if (e.target.closest("button, a, input, select")) return;
    if (e.target.closest(".run-details-panel")) return;
    if (window.getSelection()?.toString()) return;
    if (onRunSelect) onRunSelect(run);
    else openRunDetail(run.name, run.id);
  }

  let orderedRuns = $derived.by(() => {
    if (!statusRuns) return [];
    return [...statusRuns].sort(
      (a, b) => new Date(b.last_timestamp || 0) - new Date(a.last_timestamp || 0),
    );
  });

  let liveCount = $derived(orderedRuns.filter((r) => runState(r) === "training").length);
  let awaitingCount = $derived(orderedRuns.filter((r) => !r.last_timestamp).length);
  let visibleRuns = $derived(orderedRuns.filter((run) => {
    const normalizedQuery = query.trim().toLowerCase();
    const summary = searchableSummaries[runKey(run)];
    const config = runConfigs[runKey(run)] ?? runConfigs[run.name];
    const metricsText = Object.entries(run.metrics || {})
      .flatMap(([name, value]) => [name, ...Object.values(value || {})])
      .join(" ");
    const matchesSearch = !normalizedQuery ||
      `${run.name} ${metricsText} ${summary?.num_logs ?? ""} ${summary?.last_step ?? ""} ${summary?.metrics?.join(" ") ?? ""} ${configSearchText(summary?.config ?? config)}`
        .toLowerCase()
        .includes(normalizedQuery);
    const matchesFilter = filter === "all" ||
      (filter === "recent" ? runState(run) === "training" : !run.last_timestamp);
    return matchesSearch && matchesFilter;
  }));
  let successAge = $derived(lastSuccess == null ? null : Math.max(0, (nowMs - lastSuccess) / 1000));
  let stale = $derived(!snapshot && successAge != null && successAge > 15);

</script>

<div class="overview-page workspace-page">
  <PageHeader
    title="Overview"
    description={project ? `Recent activity for runs in ${project}.` : "Select a project to see run activity."}
    count={statusRuns ? statusRuns.length : null}
  />
  {#if project}
    <Quickstart guide={overviewGuide(project)} collapsible={true} />
  {/if}
  <div class="sync-bar">
    <div class="sync-info" role="status">
      <span class="sync-dot" class:warning={failed || stale}></span>
      <span>{snapshot ? "Read-only snapshot" : failed ? "Updates interrupted" : stale ? "Update delayed" : "Auto-refresh on"}</span>
      {#if lastSuccess}<span class="sync-time">Last synced {fmtAgo(successAge)}</span>{/if}
    </div>
    <button class="refresh-button" disabled={manualRefreshing || !project} onclick={refreshNow}>
      {manualRefreshing ? "Refreshing…" : failed ? "Retry now" : "Refresh"}
    </button>
  </div>
  {#if failed}
    <div class="error-banner" role="alert">
      <strong>Couldn’t update run activity.</strong>
      <span>{statusRuns == null ? "Check your connection and retry. We’ll also retry automatically." : "Showing the last successful update. We’ll retry automatically."}</span>
    </div>
  {/if}
  {#if loading && statusRuns == null}
    <LoadingTrackio />
  {:else if failed && statusRuns == null}
    <div class="empty-state"><h2>Run activity is unavailable</h2><p>Your runs will appear once the connection is restored.</p></div>
  {:else if !orderedRuns.length}
    <div class="empty-state">
      <h2>No runs in this project</h2>
      <p>Runs appear here as soon as you call <code>trackio.init()</code> and log a step:</p>
      <CodeSnippet
        code={`import trackio\n\ntrackio.init(project="${project || "my-project"}")\nfor i in range(10):\n    trackio.log({"loss": 1 / (i + 1)})\ntrackio.finish()`}
      />
    </div>
  {:else}
    <div class="summary-grid" aria-label="Project activity">
      <div class="summary-item"><span>Total runs</span><strong>{orderedRuns.length}</strong><small>In this project</small></div>
      <div class="summary-item"><span>{snapshot ? "With logged data" : "Recent activity"}</span><strong>{snapshot ? orderedRuns.length - awaitingCount : liveCount}</strong><small>{snapshot ? "Saved in this snapshot" : "Logs received in the last 2 minutes"}</small></div>
      <div class="summary-item"><span>Awaiting logs</span><strong>{awaitingCount}</strong><small>No metrics received yet</small></div>
    </div>
    <div class="runs-toolbar">
      <label class="search-field"><span class="sr-only">Search runs, metrics, and configuration</span><input type="search" placeholder="Search runs, metrics, config…" bind:value={query} /></label>
      <div class="activity-toggle" role="group" aria-label="Filter activity">
        <button class:active={filter === "all"} aria-pressed={filter === "all"} onclick={() => { filter = "all"; }}>All activity</button>
        {#if !snapshot}
          <button class:active={filter === "recent"} aria-pressed={filter === "recent"} onclick={() => { filter = "recent"; }}>Recent activity</button>
        {/if}
        <button class:active={filter === "awaiting"} aria-pressed={filter === "awaiting"} onclick={() => { filter = "awaiting"; }}>Awaiting logs</button>
      </div>
      {#if searchSummaryLoading}
        <span class="searching-details" role="status">Searching run details…</span>
      {/if}
      <span class="result-count">{visibleRuns.length} of {orderedRuns.length} runs</span>
    </div>
    <p class="activity-note">{snapshot ? "Saved metric values" : "Activity reflects received logs, not process health"}. Metrics and changes use the latest {tailRows} log entries per run.</p>
    {#if !visibleRuns.length}
      <div class="empty-state"><h2>No matching runs</h2><p>Try another name or activity filter.</p><button class="refresh-button" onclick={() => { query = ""; filter = "all"; }}>Clear filters</button></div>
    {/if}
    <div class="status-list">
      {#each visibleRuns as run (runKey(run))}
        {@const state = runState(run)}
        {@const head = headlineMetric(run)}
        {@const headDelta = head ? delta(head, head.name) : null}
        {@const rate = stepsPerMin(run)}
        {@const others = otherMetrics(run)}
        {@const expanded = !!expandedRuns[runKey(run)]}
        {@const detailsOpen = !!detailsOpenRuns[runKey(run)]}
        <!-- svelte-ignore a11y_no_noninteractive_element_interactions, a11y_click_events_have_key_events -->
        <article
          class="status-card"
          class:live={state === "training"}
          onclick={(e) => handleCardClick(e, run)}
        >
          <div class="status-line">
            <div class="status-name">
              <span class="run-dot" style:background={runColorMap[runKey(run)] ?? "var(--body-text-color-subdued)"}></span>
              <button class="run-link" title={run.name} onclick={() => onRunSelect ? onRunSelect(run) : openRunDetail(run.name, run.id)}>{run.name}</button>
              <span class="state-badge state-{state}">
                {#if state === "training"}<span class="pulse-dot"></span>{/if}
                {STATE_LABELS[state]}
              </span>
            </div>
            <div class="clock-col">
              <span class="clock-main">{run.last_timestamp ? `Last log ${fmtAgo(ageSeconds(run.last_timestamp))}` : "No logs yet"}</span>
              <span class="clock-sub">
                started {fmtAgo(ageSeconds(run.first_timestamp))}
                {#if run.last_timestamp && run.first_timestamp}
                  · span {fmtDuration((new Date(run.last_timestamp).getTime() - new Date(run.first_timestamp).getTime()) / 1000)}
                {/if}
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
              <div class="k" title={`Numeric metrics in the latest ${tailRows} log entries`}>recent metrics</div>
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
                <button class="chip chip-more" aria-expanded={expanded} onclick={() => toggleExpanded(run)}>
                  {expanded ? "show less" : `+${others.length - CHIP_LIMIT} more`}
                </button>
              {/if}
            </div>
          {/if}
          <div class="run-details-toggle-row">
            <button
              class="run-details-toggle"
              aria-expanded={detailsOpen}
              onclick={() => toggleRunDetails(run)}
            >
              {detailsOpen ? "Hide details" : "Details"}
              <span aria-hidden="true">{detailsOpen ? "−" : "+"}</span>
            </button>
          </div>
          {#if detailsOpen}
            <div class="run-details-panel">
              <RunSummaryHeader
                {project}
                run={run}
                config={runConfigs[runKey(run)] ?? runConfigs[run.name]}
              />
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
    min-height: 0;
    box-sizing: border-box;
    padding: 28px;
    overflow-y: auto;
    overflow-x: hidden;
    flex: 1;
  }
  .sync-bar, .sync-info, .runs-toolbar { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
  .sync-bar { justify-content: space-between; margin-bottom: 20px; }
  .sync-info { gap: 8px; font-size: 12px; color: var(--body-text-color); }
  .sync-time, .result-count, .activity-note { color: var(--body-text-color-subdued); font-size: 12px; }
  .sync-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--status-success); }
  .sync-dot.warning { background: var(--status-warning); }
  .refresh-button { border: 1px solid var(--border-color-primary); border-radius: var(--radius-lg); background: var(--background-fill-primary); color: var(--body-text-color); padding: 8px 14px; font: inherit; font-size: 12px; cursor: pointer; }
  .refresh-button:hover:not(:disabled) { background: var(--background-fill-secondary); }
  .refresh-button:disabled { opacity: .6; cursor: wait; }
  .error-banner { display: flex; flex-direction: column; gap: 4px; border: 1px solid color-mix(in srgb, var(--status-warning) 45%, var(--border-color-primary)); border-radius: var(--radius-lg); padding: 14px 16px; margin-bottom: 20px; background: color-mix(in srgb, var(--status-warning) 7%, var(--background-fill-primary)); color: var(--body-text-color); font-size: 13px; }
  .summary-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); border: 1px solid var(--border-color-primary); border-radius: var(--radius-xxl); background: var(--background-fill-primary); box-shadow: var(--shadow-drop); margin-bottom: 24px; }
  .summary-item { display: flex; flex-direction: column; gap: 8px; padding: 20px 24px; }
  .summary-item + .summary-item { border-left: 1px solid var(--border-color-primary); }
  .summary-item > span { font-size: 12px; color: var(--body-text-color-subdued); }
  .summary-item strong { font-size: 28px; font-weight: 600; letter-spacing: -.04em; color: var(--body-text-color); font-variant-numeric: tabular-nums; }
  .summary-item small { font-size: 11px; color: var(--body-text-color-subdued); line-height: 1.5; }
  .runs-toolbar { gap: 10px; }
  .search-field { flex: 1; min-width: 160px; max-width: 340px; }
  .search-field input { width: 100%; box-sizing: border-box; border: 1px solid var(--border-color-primary); border-radius: var(--radius-lg); padding: 10px 12px; background: var(--background-fill-primary); color: var(--body-text-color); font: inherit; font-size: 13px; }
  .search-field input::placeholder { color: var(--body-text-color-subdued); }
  .activity-toggle { display: inline-flex; align-items: center; gap: 2px; padding: 3px; border: 1px solid var(--border-color-primary); border-radius: var(--radius-lg); background: var(--background-fill-secondary); }
  .activity-toggle button { border: 0; border-radius: calc(var(--radius-lg) - 3px); padding: 7px 10px; background: transparent; color: var(--body-text-color-subdued); font: inherit; font-size: 12px; white-space: nowrap; cursor: pointer; }
  .activity-toggle button:hover { color: var(--body-text-color); }
  .activity-toggle button.active { background: var(--background-fill-primary); color: var(--body-text-color); box-shadow: var(--shadow-drop); }
  .result-count { margin-left: auto; }
  .searching-details { color: var(--body-text-color-subdued); font-size: 11px; }
  .activity-note { margin: 12px 0 18px; line-height: 1.6; }
  .sr-only { position: absolute; width: 1px; height: 1px; padding: 0; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
  button:focus-visible, input:focus-visible { outline: 2px solid var(--color-accent); outline-offset: 3px; }
  .status-list {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }
  .run-details-toggle-row { display: flex; justify-content: flex-end; margin-top: 12px; }
  .run-details-toggle { display: inline-flex; align-items: center; gap: 7px; padding: 4px 2px; border: 0; background: transparent; color: var(--body-text-color-subdued); font: inherit; font-size: 12px; cursor: pointer; }
  .run-details-toggle:hover { color: var(--body-text-color); }
  .status-card :global(.run-summary-card) { margin: 12px 0 0; box-shadow: none; }
  .status-card {
    border: 1px solid var(--border-color-primary);
    box-shadow: var(--shadow-drop);
    border-radius: var(--radius-xxl);
    padding: 18px 20px;
    background: var(--background-fill-primary);
    cursor: pointer;
    transition: border-color 0.15s, box-shadow 0.15s;
  }
  .status-card:hover {
    border-color: color-mix(
      in srgb,
      var(--body-text-color) 20%,
      var(--border-color-primary)
    );
    box-shadow: var(--shadow-drop);
  }
  .status-card.live {
    border-color: color-mix(in srgb, var(--status-success) 45%, var(--border-color-primary));
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
    color: var(--body-text-color);
    cursor: pointer;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .run-link:hover {
    color: var(--color-accent);
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
    color: var(--status-success);
    background: color-mix(in srgb, var(--status-success) 12%, transparent);
  }
  .state-idle {
    color: var(--status-warning);
    background: color-mix(in srgb, var(--status-warning) 12%, transparent);
  }
  .state-snapshot,
  .state-stopped,
  .state-unknown {
    color: var(--body-text-color-subdued);
    background: var(--background-fill-secondary);
  }
  .pulse-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--status-success);
    animation: pulse 1.6s ease-in-out infinite;
    flex-shrink: 0;
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; box-shadow: 0 0 0 0 color-mix(in srgb, var(--status-success) 35%, transparent); }
    50% { opacity: 0.6; box-shadow: 0 0 0 4px transparent; }
  }
  .big-step {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 3px;
    white-space: nowrap;
    padding-left: 20px;
    border-left: 1px solid var(--border-color-primary);
  }
  .big-step-label {
    font-size: 10.5px;
    color: var(--body-text-color-subdued);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    line-height: 1;
  }
  .big-step-value {
    font-size: 22px;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    color: var(--body-text-color);
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
    color: var(--body-text-color);
    font-variant-numeric: tabular-nums;
  }
  .clock-sub {
    font-size: 11.5px;
    color: var(--body-text-color-subdued);
    font-variant-numeric: tabular-nums;
  }
  .kv {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 10px;
    margin-top: 16px;
  }
  .kv-cell {
    border-radius: var(--radius-lg, 8px);
    padding: 10px 12px;
    background: var(--background-fill-secondary);
    min-width: 0;
  }
  .kv-cell .k {
    font-size: 11px;
    color: var(--body-text-color-subdued);
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
    color: var(--body-text-color);
  }
  .kv-cell .u {
    margin-left: 4px;
    font-size: 11px;
    font-weight: 400;
    color: var(--body-text-color-subdued);
  }
  .delta {
    margin-left: 6px;
    font-size: 12px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }
  .delta.good { color: var(--status-success); }
  .delta.bad { color: var(--status-danger); }
  .delta.neutral { color: var(--body-text-color-subdued); }
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
    border: 1px solid var(--border-color-primary);
    border-radius: 999px;
    background: var(--background-fill-primary);
    font-size: 12px;
  }
  .chip-name {
    color: var(--body-text-color-subdued);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 220px;
  }
  .chip-value {
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    color: var(--body-text-color);
  }
  .chip-more {
    cursor: pointer;
    font: inherit;
    font-size: 12px;
    color: var(--color-accent);
    background: none;
  }
  .chip-more:hover { text-decoration: underline; }
  .empty-state {
    border: 1px dashed var(--border-color-primary);
    border-radius: var(--radius-xxl);
    padding: 32px;
    color: var(--body-text-color-subdued);
  }
  .empty-state h2 {
    color: var(--body-text-color);
    font-size: 16px;
    margin-bottom: 8px;
  }
  .empty-state :global(pre) {
    margin-top: 12px;
    padding: 12px;
    border-radius: 8px;
    background: var(--background-fill-secondary);
    overflow-x: auto;
    font-size: 12.5px;
  }
  @media (max-width: 700px) {
    .overview-page { padding: 20px 16px; }
    .summary-item { padding: 16px 12px; }
    .summary-item strong { font-size: 24px; }
    .summary-item small { display: none; }
    .status-card { padding: 16px; }
    .status-line { gap: 14px; }
    .status-name { flex-basis: 100%; }
    .run-link { flex: 1; text-align: left; }
    .clock-col { margin-left: 0; text-align: left; white-space: normal; }
    .kv { grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); }
    .result-count { flex-basis: 100%; }
    .chip-name { max-width: 150px; }
    .sync-time { flex-basis: 100%; margin-left: 15px; }
    .big-step { padding-left: 0; border-left: none; align-items: flex-start; }
  }
  @media (prefers-reduced-motion: reduce) { .pulse-dot { animation: none; } .status-card { transition: none; } }
</style>
