<script>
  import PageHeader from "../components/PageHeader.svelte";
  import CodeSnippet from "../components/CodeSnippet.svelte";
  import { onMount } from "svelte";
  import { getQueryParam, navigateTo } from "../lib/router.js";
  import LinePlot from "../components/LinePlot.svelte";
  import BarPlot from "../components/BarPlot.svelte";
  import HistogramPlot from "../components/HistogramPlot.svelte";
  import Accordion from "../components/Accordion.svelte";
  import LoadingTrackio from "../components/LoadingTrackio.svelte";
  import RunComparer from "../components/RunComparer.svelte";
  import { getLogsBatch } from "../lib/api.js";
  import {
    getMetricsPollIntervalMs,
    isRateLimitCooldownActive,
    isTabHidden,
  } from "../lib/hostPolling.js";
  import {
    processRunData,
    resolveXColumn,
    getMetricColumns,
    groupMetricsByPrefix,
    filterMetricsByRegex,
    computeMetricPlotData,
    logsHaveNewData,
  } from "../lib/dataProcessing.js";
  import { buildColorMap } from "../lib/stores.js";
  import {
    AUTO_PANELS_PER_ROW,
    getPlotColumns,
    isAutoPanels,
  } from "../lib/plotLayout.js";

  let {
    project = null,
    selectedRuns = [],
    allRuns = [],
    runConfigs = {},
    smoothing = 10,
    panelsPerRow = AUTO_PANELS_PER_ROW,
    xAxis = "step",
    logScaleX = false,
    logScaleY = false,
    metricFilter = "",
    showHeaders = true,
    showComparer = false,
    appBootstrapReady = false,
    plotOrder = [],
    realtimeEnabled = true,
    // eslint-disable-next-line no-useless-assignment -- bindable out-prop to parent
    metricColumns = $bindable([]),
  } = $props();

  let masterData = $state([]);
  let xColumn = $state("step");
  let metrics = $state([]);
  let histogramMetrics = $state([]);
  let histogramItems = $state({});
  let singlePointMetrics = $state(new Set());
  let xLim = $state(null);
  let hasLoaded = $state(false);
  let metricOrder = $state({});
  let dragState = $state({ group: null, index: -1 });

  let rawDataCache = new Map();
  let refreshTimer = null;
  const MAX_BATCH_RUNS = 64;

  let colorMap = $derived(buildColorMap(allRuns));

  let metricGroups = $derived.by(() => {
    let filtered = metricFilter
      ? filterMetricsByRegex(metrics, metricFilter)
      : metrics;
    return groupMetricsByPrefix(filtered, plotOrder);
  });

  let groupNames = $derived(Object.keys(metricGroups));

  let filteredHistogramMetrics = $derived(
    metricFilter
      ? filterMetricsByRegex(histogramMetrics, metricFilter)
      : histogramMetrics,
  );

  let selectedGroup = $state("all");

  function groupMetricCount(name) {
    const g = metricGroups[name];
    if (!g) return 0;
    return (
      g.direct.length +
      Object.values(g.subgroups).reduce((n, arr) => n + arr.length, 0)
    );
  }

  let visibleGroupNames = $derived(
    selectedGroup === "all"
      ? groupNames
      : groupNames.filter((g) => g === selectedGroup),
  );

  let showHistogramSection = $derived(
    filteredHistogramMetrics.length > 0 &&
      (selectedGroup === "all" || selectedGroup === "histograms"),
  );

  let totalMetricCount = $derived(
    groupNames.reduce((n, g) => n + groupMetricCount(g), 0) +
      filteredHistogramMetrics.length,
  );

  let showGroupChips = $derived(
    groupNames.length + (filteredHistogramMetrics.length > 0 ? 1 : 0) > 1,
  );

  $effect(() => {
    if (selectedGroup === "all") return;
    const stillExists =
      selectedGroup === "histograms"
        ? filteredHistogramMetrics.length > 0
        : groupNames.includes(selectedGroup);
    if (!stillExists) selectedGroup = "all";
  });

  function getPlotResult(metric) {
    return computeMetricPlotData(masterData, xColumn, metric, xLim);
  }

  let autoLayout = $derived(isAutoPanels(panelsPerRow));

  function getGroupCols(items) {
    return getPlotColumns(panelsPerRow, items.length);
  }

  function getOrderedMetrics(key, items) {
    const order = metricOrder[key];
    if (!order) return items;
    const ordered = [];
    for (const m of order) {
      if (items.includes(m)) ordered.push(m);
    }
    for (const m of items) {
      if (!ordered.includes(m)) ordered.push(m);
    }
    return ordered;
  }

  function handleDragStart(groupKey, index, e) {
    dragState = { group: groupKey, index };
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", "");
  }

  function handleDragOver(groupKey, index, e) {
    if (dragState.group !== groupKey) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
  }

  function handleDrop(groupKey, index, metrics, e) {
    e.preventDefault();
    if (dragState.group !== groupKey || dragState.index === index) {
      dragState = { group: null, index: -1 };
      return;
    }
    const ordered = [...metrics];
    const [moved] = ordered.splice(dragState.index, 1);
    ordered.splice(index, 0, moved);
    metricOrder = { ...metricOrder, [groupKey]: ordered };
    dragState = { group: null, index: -1 };
  }

  function extractHistograms(originals) {
    const latest = new Map();
    for (const r of originals) {
      for (const [key, value] of Object.entries(r)) {
        if (
          !value ||
          typeof value !== "object" ||
          value._type !== "trackio.histogram"
        )
          continue;
        if (!Array.isArray(value.bins) || value.bins.length < 2) continue;
        const mapKey = `${key}\0${r.series_key}`;
        const prev = latest.get(mapKey);
        if (!prev || (r.step ?? 0) >= prev.step) {
          latest.set(mapKey, {
            metric: key,
            key: r.series_key,
            label: r.run,
            step: r.step ?? 0,
            bins: value.bins,
            values: value.values ?? [],
          });
        }
      }
    }
    const byMetric = {};
    for (const item of latest.values()) {
      if (!byMetric[item.metric]) byMetric[item.metric] = [];
      byMetric[item.metric].push(item);
    }
    histogramItems = byMetric;
    histogramMetrics = Object.keys(byMetric).sort();
  }

  function processFromCache() {
    if (!project || selectedRuns.length === 0) {
      masterData = [];
      metrics = [];
      histogramMetrics = [];
      histogramItems = {};
      return;
    }

    const allRows = [];
    const runXColumns = [];
    for (const run of selectedRuns) {
      const logs = rawDataCache.get(run.id ?? run.name);
      if (!logs) continue;
      const result = processRunData(logs, run, smoothing, xAxis, logScaleX, logScaleY);
      if (result) {
        allRows.push(...result.rows);
        runXColumns.push(result.xColumn);
      }
    }
    xColumn = resolveXColumn(runXColumns, xAxis);
    masterData = allRows;

    const originals = allRows.filter(
      (r) => r.data_type === "original" || !r.data_type,
    );
    extractHistograms(originals);
    const allCols = getMetricColumns(originals).filter(
      (c) => c !== "run" && c !== "data_type" && c !== "x_axis",
    );
    const cols = allCols.filter((c) => c !== xColumn);
    metrics = cols;
    metricColumns = allCols;

    const countPerRunMetric = new Map();
    for (const r of originals) {
      const run = r.series_key;
      for (const col of cols) {
        if (r[col] == null) continue;
        const key = `${col}\0${run}`;
        countPerRunMetric.set(key, (countPerRunMetric.get(key) || 0) + 1);
      }
    }
    const sp = new Set(cols);
    for (const [key, count] of countPerRunMetric) {
      if (count > 1) {
        sp.delete(key.split("\0")[0]);
      }
    }
    singlePointMetrics = sp;
  }

  async function fetchLogsForRuns(runs) {
    const results = [];
    for (let i = 0; i < runs.length; i += MAX_BATCH_RUNS) {
      const chunk = runs.slice(i, i + MAX_BATCH_RUNS);
      const batch = await getLogsBatch(project, chunk, { scalar_only: true });
      results.push(...batch);
    }
    return results;
  }

  async function fetchNewRuns() {
    if (!appBootstrapReady) {
      hasLoaded = false;
      return;
    }
    if (!project || selectedRuns.length === 0) {
      masterData = [];
      metrics = [];
      histogramMetrics = [];
      histogramItems = {};
      hasLoaded = true;
      return;
    }

    const needFetch = selectedRuns.filter((run) => {
      const runKey = run.id ?? run.name;
      return !rawDataCache.has(runKey);
    });
    let fetched = false;
    if (needFetch.length > 0) {
      try {
        const batch = await fetchLogsForRuns(needFetch);
        for (const entry of batch) {
          const runKey = entry.run_id ?? entry.run;
          rawDataCache.set(runKey, entry.logs);
          fetched = true;
        }
      } catch (e) {
        console.error("Failed to load metric logs:", e);
      }
    }

    if (fetched || !hasLoaded) {
      processFromCache();
    }
    hasLoaded = true;
  }

  async function refreshCachedRuns() {
    if (!realtimeEnabled) return;
    if (!project || selectedRuns.length === 0) return;
    if (isTabHidden()) return;
    if (isRateLimitCooldownActive()) return;

    try {
      const batch = await fetchLogsForRuns(selectedRuns);
      let changed = false;
      for (const entry of batch) {
        const runKey = entry.run_id ?? entry.run;
        const logs = entry.logs;
        const prev = rawDataCache.get(runKey);
        if (!prev || logsHaveNewData(prev, logs)) {
          rawDataCache.set(runKey, logs);
          changed = true;
        }
      }
      if (changed) {
        processFromCache();
      }
    } catch (e) {
      console.error("Failed to refresh metric logs:", e);
    }
  }

  $effect(() => {
    project;
    selectedRuns;
    appBootstrapReady;
    rawDataCache = project ? rawDataCache : new Map();
    fetchNewRuns();
  });

  $effect(() => {
    smoothing;
    xAxis;
    logScaleX;
    logScaleY;
    if (hasLoaded) {
      processFromCache();
    }
  });

  let lastXSemantics = null;

  $effect(() => {
    const semantics = `${project}\0${xAxis}\0${logScaleX}`;
    if (lastXSemantics !== null && semantics !== lastXSemantics) {
      xLim = null;
    }
    lastXSemantics = semantics;
  });

  onMount(() => {
    const xMin = getQueryParam("xmin");
    const xMax = getQueryParam("xmax");
    if (xMin != null && xMin !== "" && xMax != null && xMax !== "") {
      const lo = parseFloat(xMin);
      const hi = parseFloat(xMax);
      if (!Number.isNaN(lo) && !Number.isNaN(hi) && lo < hi) {
        xLim = [lo, hi];
      }
    }
    refreshTimer = setInterval(
      refreshCachedRuns,
      getMetricsPollIntervalMs(),
    );
    return () => {
      if (refreshTimer) clearInterval(refreshTimer);
    };
  });

  function handlePlotSelect(range) {
    if (range && range.length === 2) {
      xLim = range;
    }
  }

  function handleResetZoom() {
    xLim = null;
  }

</script>

<div class="metrics-page workspace-page">
  <PageHeader title="Metrics" description="Compare training progress across your selected runs." />
  {#if !appBootstrapReady || !hasLoaded}
    <LoadingTrackio />
  {:else if !project}
    <div class="empty-state">
      <h2>No projects</h2>
      <p>
        Create a project by calling <code>trackio.init(project="…")</code> in your training script:
      </p>
      <CodeSnippet
        code={'import trackio\n\ntrackio.init(project="my-project")\nfor i in range(10):\n    trackio.log({"loss": 1 / (i + 1)})\ntrackio.finish()'}
      />
    </div>
  {:else if selectedRuns.length === 0}
    <div class="empty-state">
      <h2>No run selected</h2>
      <p>Select one or more runs in the sidebar.</p>
    </div>
  {:else if masterData.length === 0}
    <div class="empty-state">
      <h2>Start logging with Trackio</h2>
      <p>
        Call <code>trackio.init()</code> to create a run, <code>trackio.log()</code> to log metrics,
        and <code>trackio.finish()</code> when the run is done:
      </p>
      <CodeSnippet
        code={`import trackio\n\ntrackio.init(project="${project}")\nfor i in range(10):\n    trackio.log({"loss": 1 / (i + 1)})\ntrackio.finish()`}
      />
      <p>
        Training an LLM? Stage-specific recipes (pretraining, SFT, RLHF,
        evals) with suggested metrics live in
        <button class="inline-link" onclick={() => navigateTo("settings")}>Settings</button>.
      </p>
    </div>
  {:else}
    {#if showComparer}
      <RunComparer runs={selectedRuns} {runConfigs} {colorMap} />
    {/if}
    {#if showGroupChips}
      <div class="group-chips" aria-label="Metric groups">
        <button
          class="group-chip"
          class:active={selectedGroup === "all"}
          onclick={() => (selectedGroup = "all")}
        >
          all <span class="chip-count">{totalMetricCount}</span>
        </button>
        {#each groupNames as g}
          <button
            class="group-chip"
            class:active={selectedGroup === g}
            onclick={() => (selectedGroup = g)}
          >
            {g} <span class="chip-count">{groupMetricCount(g)}</span>
          </button>
        {/each}
        {#if filteredHistogramMetrics.length > 0}
          <button
            class="group-chip"
            class:active={selectedGroup === "histograms"}
            onclick={() => (selectedGroup = "histograms")}
          >
            histograms <span class="chip-count">{filteredHistogramMetrics.length}</span>
          </button>
        {/if}
      </div>
    {/if}
    {#each visibleGroupNames as groupName}
      {@const group = metricGroups[groupName]}
      {@const directKey = `${groupName}:direct`}
      {@const orderedDirect = getOrderedMetrics(directKey, group.direct)}
      {@const directCols = getGroupCols(orderedDirect)}
      {@const directCount = group.direct.length}
      {@const subCount = Object.values(group.subgroups).reduce((a, b) => a + b.length, 0)}
      {@const totalCount = directCount + subCount}

      <Accordion
        label="{groupName} ({totalCount})"
        open={true}
        hidden={!showHeaders}
      >
        {#if orderedDirect.length > 0}
          <div class="plot-grid" class:auto={autoLayout} style="--cols: {directCols}">
            {#each orderedDirect as metric, i}
              {@const plotResult = getPlotResult(metric)}
              {@const plotData = plotResult.data}
              {@const yExtent = plotResult.yExtent}
              {@const useBar = singlePointMetrics.has(metric)}
              {@const directTitle = showHeaders ? metric.split("/").slice(1).join("/") || metric : metric}
              {#if plotData.length > 0}
                {#if useBar}
                  <BarPlot
                    data={plotData}
                    y={metric}
                    title={directTitle}
                    colorField="series_key"
                    colorDisplayField="run"
                    {colorMap}
                    draggable={true}
                    ondragstart={(e) => handleDragStart(directKey, i, e)}
                    ondragover={(e) => handleDragOver(directKey, i, e)}
                    ondrop={(e) => handleDrop(directKey, i, orderedDirect, e)}
                  />
                {:else}
                  <LinePlot
                    data={plotData}
                    x={xColumn}
                    y={metric}
                    title={directTitle}
                    colorField="series_key"
                    colorDisplayField="run"
                    {colorMap}
                    {xLim}
                    {yExtent}
                    onSelect={handlePlotSelect}
                    onResetZoom={handleResetZoom}
                    draggable={true}
                    ondragstart={(e) => handleDragStart(directKey, i, e)}
                    ondragover={(e) => handleDragOver(directKey, i, e)}
                    ondrop={(e) => handleDrop(directKey, i, orderedDirect, e)}
                  />
                {/if}
              {/if}
            {/each}
          </div>
        {/if}

        <div class="subgroup-list">
          {#each Object.entries(group.subgroups) as [subName, subMetrics]}
            {@const subKey = `${groupName}:${subName}`}
            {@const orderedSub = getOrderedMetrics(subKey, subMetrics)}
            {@const subCols = getGroupCols(orderedSub)}
            <Accordion
              label="{subName} ({subMetrics.length})"
              open={true}
              hidden={!showHeaders}
            >
              <div class="plot-grid" class:auto={autoLayout} style="--cols: {subCols}">
                {#each orderedSub as metric, i}
                  {@const plotResult = getPlotResult(metric)}
                  {@const plotData = plotResult.data}
                  {@const yExtent = plotResult.yExtent}
                  {@const useBar = singlePointMetrics.has(metric)}
                  {@const subTitle = showHeaders ? metric.split("/").slice(2).join("/") || metric : metric}
                  {#if plotData.length > 0}
                    {#if useBar}
                      <BarPlot
                        data={plotData}
                        y={metric}
                        title={subTitle}
                        colorField="series_key"
                        colorDisplayField="run"
                        {colorMap}
                        draggable={true}
                        ondragstart={(e) => handleDragStart(subKey, i, e)}
                        ondragover={(e) => handleDragOver(subKey, i, e)}
                        ondrop={(e) => handleDrop(subKey, i, orderedSub, e)}
                      />
                    {:else}
                      <LinePlot
                        data={plotData}
                        x={xColumn}
                        y={metric}
                        title={subTitle}
                        colorField="series_key"
                        colorDisplayField="run"
                        {colorMap}
                        {xLim}
                        {yExtent}
                        onSelect={handlePlotSelect}
                        onResetZoom={handleResetZoom}
                        draggable={true}
                        ondragstart={(e) => handleDragStart(subKey, i, e)}
                        ondragover={(e) => handleDragOver(subKey, i, e)}
                        ondrop={(e) => handleDrop(subKey, i, orderedSub, e)}
                      />
                    {/if}
                  {/if}
                {/each}
              </div>
            </Accordion>
          {/each}
        </div>
      </Accordion>
    {/each}

    {#if showHistogramSection}
      <Accordion
        label="histograms ({filteredHistogramMetrics.length})"
        open={true}
        hidden={!showHeaders}
      >
        <div
          class="plot-grid"
          class:auto={autoLayout}
          style="--cols: {getGroupCols(filteredHistogramMetrics)}"
        >
          {#each filteredHistogramMetrics as metric}
            <HistogramPlot
              items={histogramItems[metric]}
              title={metric}
              {metric}
              {colorMap}
            />
          {/each}
        </div>
      </Accordion>
    {/if}
  {/if}
</div>

<style>
  .metrics-page {
    min-width: 0;
    box-sizing: border-box;
    padding: 28px;
    overflow-y: auto;
    flex: 1;
    min-height: 0;
  }
  .plot-grid {
    --plot-gap: 14px;
    --plot-min-width: 280px;
    --plot-max-cols: 5;
    display: grid;
    grid-template-columns: repeat(var(--cols, 1), minmax(0, 1fr));
    gap: var(--plot-gap);
  }
  .plot-grid.auto {
    grid-template-columns: repeat(
      auto-fill,
      minmax(
        min(
          100%,
          max(
            var(--plot-min-width),
            (100% - (var(--plot-max-cols) - 1) * var(--plot-gap)) /
              var(--plot-max-cols) - 0.01px
          )
        ),
        1fr
      )
    );
  }
  .plot-grid :global(.plot-container) {
    min-width: 0;
    width: 100%;
  }
  .subgroup-list {
    margin-top: 16px;
  }
  .inline-link {
    padding: 0;
    border: none;
    background: none;
    color: var(--color-accent, #f97316);
    font: inherit;
    font-weight: 500;
    cursor: pointer;
  }
  .inline-link:hover {
    text-decoration: underline;
  }
  .group-chips {
    position: sticky;
    top: 0;
    z-index: 5;
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin: 0 0 14px;
    padding: 8px 0;
    background: var(--background-fill-primary, white);
    box-shadow: 0 -28px 0 0 var(--background-fill-primary, white);
  }
  .group-chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 12px;
    border: 1px solid var(--border-color-primary, #e5e7eb);
    border-radius: 999px;
    background: var(--background-fill-primary, white);
    color: var(--body-text-color-subdued, #6b7280);
    font: inherit;
    font-size: 12.5px;
    font-weight: 500;
    cursor: pointer;
    transition: color 0.15s, border-color 0.15s, background-color 0.15s;
  }
  .group-chip:hover {
    color: var(--body-text-color, #1f2937);
  }
  .group-chip.active {
    border-color: var(--color-accent, #f97316);
    background: var(--color-accent-soft, #fff7ed);
    color: var(--body-text-color, #1f2937);
  }
  .chip-count {
    font-size: 11px;
    color: var(--body-text-color-subdued, #9ca3af);
    font-variant-numeric: tabular-nums;
  }
  @media (max-width: 700px) {
    .metrics-page { padding: 20px 16px; }
  }
</style>
