<script>
  let {
    alerts = [],
    dismissAccess = { visible: false, allowed: false, reason: null },
    onDismiss = null,
  } = $props();

  const BADGES = { info: "🔵", warn: "🟡", error: "🔴" };
  let expanded = $state({});
  let filterLevel = $state(null);
  let collapsed = $state(false);

  let filtered = $derived(
    filterLevel ? alerts.filter((a) => a.level === filterLevel) : alerts,
  );

  function toggleExpand(id) {
    expanded = { ...expanded, [id]: !expanded[id] };
  }

  function dismiss(ids) {
    if (!dismissAccess.allowed || !onDismiss || ids.length === 0) return;
    onDismiss(ids);
  }
</script>

{#if alerts.length > 0}
  <div class="alert-panel" class:collapsed>
    <div class="alert-header" role="button" tabindex="0" onclick={() => (collapsed = !collapsed)} onkeydown={(e) => e.key === "Enter" && (collapsed = !collapsed)}>
      <span class="alert-title">Alerts ({alerts.length})</span>
      {#if !collapsed}
        <div class="filter-pills">
          <button
            class="pill"
            class:active={filterLevel === null}
            onclick={(e) => {
              e.stopPropagation();
              filterLevel = null;
            }}
            >All</button
          >
          <button
            class="pill"
            class:active={filterLevel === "info"}
            onclick={(e) => {
              e.stopPropagation();
              filterLevel = "info";
            }}
            >🔵 Info</button
          >
          <button
            class="pill"
            class:active={filterLevel === "warn"}
            onclick={(e) => {
              e.stopPropagation();
              filterLevel = "warn";
            }}
            >🟡 Warn</button
          >
          <button
            class="pill"
            class:active={filterLevel === "error"}
            onclick={(e) => {
              e.stopPropagation();
              filterLevel = "error";
            }}
            >🔴 Error</button
          >
        </div>
      {/if}
      <svg class="collapse-icon" class:rotated={collapsed} width="14" height="14" viewBox="0 0 16 16" fill="none">
        <path d="M4 6L8 10L12 6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    </div>
    {#if !collapsed}
    <div class="alert-list">
      {#each filtered as alert (alert.id)}
        <div class="alert-item" class:expanded={expanded[alert.id]}>
          <div class="alert-line">
            <button class="alert-row" onclick={() => toggleExpand(alert.id)}>
              <span>{BADGES[alert.level] || ""}</span>
              <span class="alert-text">{alert.title}</span>
              <span class="alert-meta">{alert.meta || ""}</span>
            </button>
            {#if dismissAccess.visible}
              <button
                class="dismiss-btn"
                title={dismissAccess.allowed ? "Dismiss" : dismissAccess.reason}
                aria-label={`Dismiss alert: ${alert.title}`}
                disabled={!dismissAccess.allowed}
                onclick={() => dismiss([alert.id])}
              >
                <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
                  <path d="M4 4L12 12M12 4L4 12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                </svg>
              </button>
            {/if}
          </div>
          {#if expanded[alert.id] && alert.text}
            <div class="alert-detail">{alert.text}</div>
          {/if}
        </div>
      {/each}
    </div>
    {#if dismissAccess.visible && filtered.length > 0}
      <div class="alert-footer">
        {#if dismissAccess.allowed}
          <button
            class="dismiss-all"
            onclick={() => dismiss(filtered.map((a) => a.id))}
            >{filterLevel ? `Dismiss all ${filterLevel}` : "Dismiss all"} ({filtered.length})</button
          >
        {:else}
          <span class="dismiss-hint">{dismissAccess.reason}</span>
        {/if}
      </div>
    {/if}
    {/if}
  </div>
{/if}

<style>
  .alert-panel {
    position: fixed;
    bottom: 16px;
    right: 16px;
    width: 380px;
    max-height: 400px;
    background: var(--background-fill-primary, white);
    border: 1px solid var(--border-color-primary, #e5e7eb);
    border-radius: var(--radius-lg, 8px);
    box-shadow: var(--shadow-drop-lg);
    z-index: 1000;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }
  .alert-panel.collapsed {
    max-height: none;
  }
  .alert-header {
    padding: 10px 12px;
    border: none;
    border-bottom: 1px solid var(--border-color-primary, #e5e7eb);
    background: none;
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: space-between;
    cursor: pointer;
    gap: 8px;
  }
  .alert-panel.collapsed .alert-header {
    border-bottom: none;
  }
  .collapse-icon {
    color: var(--body-text-color-subdued, #9ca3af);
    flex-shrink: 0;
    transition: transform 0.15s;
  }
  .collapse-icon.rotated {
    transform: rotate(-90deg);
  }
  .alert-title {
    white-space: nowrap;
    font-size: 13px;
    font-weight: 600;
    color: var(--body-text-color, #1f2937);
  }
  .filter-pills {
    display: flex;
    gap: 4px;
  }
  .pill {
    white-space: nowrap;
    border: 1px solid var(--border-color-primary, #e5e7eb);
    border-radius: var(--radius-xxl, 22px);
    padding: 2px 8px;
    font-size: 11px;
    background: var(--background-fill-secondary, #f9fafb);
    color: var(--body-text-color-subdued, #6b7280);
    cursor: pointer;
  }
  .pill.active {
    background: var(--color-accent, #f97316);
    color: white;
    border-color: var(--color-accent, #f97316);
  }
  .alert-list {
    overflow-y: auto;
    flex: 1;
  }
  .alert-item {
    border-bottom: 1px solid var(--border-color-primary, #e5e7eb);
  }
  .alert-line {
    display: flex;
    align-items: center;
  }
  .alert-line:hover {
    background: var(--background-fill-secondary, #f9fafb);
  }
  .dismiss-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    width: 24px;
    height: 24px;
    margin-right: 8px;
    border: none;
    border-radius: var(--radius-md, 6px);
    background: none;
    color: var(--body-text-color-subdued, #9ca3af);
    cursor: pointer;
  }
  .dismiss-btn:disabled {
    cursor: not-allowed;
    opacity: 0.35;
  }
  .dismiss-btn:disabled:hover {
    color: var(--body-text-color-subdued, #9ca3af);
    background: none;
  }
  .dismiss-hint {
    font-size: 11px;
    color: var(--body-text-color-subdued, #6b7280);
    text-align: right;
  }
  .dismiss-btn:hover {
    color: var(--body-text-color, #1f2937);
    background: color-mix(in srgb, var(--body-text-color, #1f2937) 8%, transparent);
  }
  .alert-footer {
    display: flex;
    justify-content: flex-end;
    padding: 6px 12px;
    border-top: 1px solid var(--border-color-primary, #e5e7eb);
  }
  .dismiss-all {
    border: none;
    background: none;
    padding: 2px 4px;
    font-size: 11px;
    color: var(--body-text-color-subdued, #6b7280);
    cursor: pointer;
    white-space: nowrap;
  }
  .dismiss-all:hover {
    color: var(--body-text-color, #1f2937);
    text-decoration: underline;
  }
  .alert-row {
    display: flex;
    align-items: center;
    gap: 8px;
    flex: 1;
    min-width: 0;
    padding: 8px 12px;
    border: none;
    background: none;
    text-align: left;
    cursor: pointer;
    font-size: var(--text-sm, 12px);
  }
  .alert-text {
    flex: 1;
    color: var(--body-text-color, #1f2937);
  }
  .alert-meta {
    font-size: var(--text-xs, 10px);
    color: var(--body-text-color-subdued, #9ca3af);
    white-space: nowrap;
  }
  .alert-detail {
    padding: 4px 12px 8px 32px;
    font-size: var(--text-sm, 12px);
    color: var(--body-text-color-subdued, #6b7280);
  }
</style>
