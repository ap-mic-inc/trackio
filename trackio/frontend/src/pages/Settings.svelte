<script>
  import CodeSnippet from "../components/CodeSnippet.svelte";
  import PageHeader from "../components/PageHeader.svelte";
  import { copyTextToClipboard } from "../lib/clipboard.js";
  import {
    createMyApiToken,
    getApiBase,
    getMyApiTokens,
    getStorageUsage,
    revokeMyApiToken,
  } from "../lib/api.js";
  import {
    dashboardServerUrl,
    maskedToken,
    tokenUsageSnippet,
  } from "../lib/apiTokens.js";
  import {
    STORAGE_CATEGORIES,
    diskStatus,
    formatBytes,
    storageRows,
  } from "../lib/storage.js";
  import {
    getThemePreference,
    setThemePreference,
  } from "../lib/theme.js";

  let {
    spaceId = null,
    selectedProject = null,
    projects = [],
    signedIn = false,
  } = $props();

  let apiTokens = $state([]);
  let apiTokenUser = $state(null);
  let apiTokenCanWrite = $state(true);
  let apiTokenError = $state(null);
  let newTokenName = $state("");
  let creatingToken = $state(false);
  let freshToken = $state(null);
  let revokingTokenId = $state(null);
  let serverUrl = $derived(dashboardServerUrl(window.location, getApiBase()));
  let usageSnippet = $derived(tokenUsageSnippet(serverUrl, freshToken?.token ?? null));

  async function loadApiTokens() {
    apiTokenError = null;
    try {
      const data = await getMyApiTokens();
      apiTokens = data.tokens ?? [];
      apiTokenUser = data.user ?? null;
      apiTokenCanWrite = data.can_write !== false;
    } catch (error) {
      apiTokenError = String(error?.message || error);
    }
  }

  $effect(() => {
    if (signedIn) loadApiTokens();
  });

  async function createToken(event) {
    event.preventDefault();
    creatingToken = true;
    apiTokenError = null;
    try {
      freshToken = await createMyApiToken(newTokenName);
      newTokenName = "";
      await loadApiTokens();
    } catch (error) {
      apiTokenError = String(error?.message || error);
    } finally {
      creatingToken = false;
    }
  }

  async function revokeToken(token) {
    if (!window.confirm(`Revoke token "${token.name}"? Scripts using it will stop logging.`)) return;
    revokingTokenId = token.id;
    apiTokenError = null;
    try {
      await revokeMyApiToken(token.id);
      if (freshToken?.id === token.id) freshToken = null;
      await loadApiTokens();
    } catch (error) {
      apiTokenError = String(error?.message || error);
    } finally {
      revokingTokenId = null;
    }
  }

  let storage = $state(null);
  let storageLoading = $state(false);
  let storageError = $state(null);
  let storageTable = $derived(storageRows(storage, selectedProject));
  let disk = $derived(diskStatus(storage?.disk));

  async function loadStorage() {
    storageLoading = true;
    storageError = null;
    try {
      storage = await getStorageUsage();
    } catch (error) {
      storageError = String(error?.message || error);
    } finally {
      storageLoading = false;
    }
  }

  $effect(() => {
    loadStorage();
  });

  let themeChoice = $state(getThemePreference());
  let copiedIdx = $state(null);
  let cliProject = $state(null);
  let selectedAgent = $state("claude");
  let agentCopied = $state(false);
  let exampleCopied = $state(false);

  const agents = [
    { id: "claude", label: "Claude Code", flag: "--claude" },
    { id: "codex", label: "Codex", flag: "--codex" },
    { id: "cursor", label: "Cursor", flag: "--cursor" },
    { id: "opencode", label: "OpenCode", flag: "--opencode" },
  ];

  let agentInstallCmd = $derived(
    `trackio skills add ${agents.find((a) => a.id === selectedAgent)?.flag}`
  );

  let agentExample = $derived.by(() => {
    const proj = cliProject || "<project>";
    const examples = {
      claude: `Use the trackio skill to look at the runs in project "${proj}" and find at which step the loss started diverging. Summarize what happened.`,
      codex: `Use the trackio skill to pull the latest metrics for project "${proj}" and tell me which run has the best final eval accuracy.`,
      cursor: `Use the trackio skill to compare the last two runs in project "${proj}" and explain why the learning rate change affected convergence.`,
      opencode: `Use the trackio skill to get a summary of project "${proj}" and flag any runs where the loss spiked unexpectedly.`,
    };
    return examples[selectedAgent];
  });

  $effect(() => {
    projects;
    selectedProject;

    if (cliProject && projects.includes(cliProject)) return;
    if (selectedProject && projects.includes(selectedProject)) {
      cliProject = selectedProject;
      return;
    }
    cliProject = projects[0] ?? selectedProject ?? null;
  });

  function switchTheme(value) {
    themeChoice = value;
    setThemePreference(value);
  }

  function spaceFlag() {
    return spaceId ? ` --space ${spaceId}` : "";
  }

  let commands = $derived.by(() => {
    const sf = spaceFlag();
    const proj = cliProject || "<project>";
    return [
      { title: "Launch dashboard", cmd: `trackio show` },
      { title: "Launch dashboard (project)", cmd: `trackio show --project "${proj}"` },
      { title: "List projects", cmd: `trackio${sf} list projects` },
      { title: "List runs", cmd: `trackio${sf} list runs --project "${proj}"` },
      { title: "List metrics", cmd: `trackio${sf} list metrics --project "${proj}" --run <run>` },
      { title: "Project summary", cmd: `trackio${sf} get project --project "${proj}"` },
      { title: "Run summary", cmd: `trackio${sf} get run --project "${proj}" --run <run>` },
      { title: "Sync to HF Space", cmd: `trackio sync${sf} --project "${proj}"` },
      { title: "Check sync status", cmd: `trackio status` },
    ];
  });

  async function copyCommand(cmd, idx) {
    if (!(await copyTextToClipboard(cmd))) return;
    copiedIdx = idx;
    setTimeout(() => {
      if (copiedIdx === idx) copiedIdx = null;
    }, 1500);
  }

  async function copyText(text, which) {
    if (!(await copyTextToClipboard(text))) return;
    if (which === "agent") {
      agentCopied = true;
      setTimeout(() => { agentCopied = false; }, 1500);
    } else {
      exampleCopied = true;
      setTimeout(() => { exampleCopied = false; }, 1500);
    }
  }
</script>

<div class="settings-page workspace-page">
  <PageHeader title="Settings" description="Customize your workspace and connect your development tools." />

  <div class="two-col">
    <div class="col col-left">
      {#if signedIn}
        <section class="settings-section" aria-labelledby="api-tokens-title">
          <h3 class="section-title" id="api-tokens-title">API tokens</h3>
          <p class="section-desc">
            Personal tokens let training scripts log to this server as
            {#if apiTokenUser}<strong>{apiTokenUser}</strong>{:else}you{/if}.
            Runs are attributed to you and follow your current role; revoke a
            token to cut off every script using it.
          </p>
          {#if !apiTokenCanWrite}
            <p class="token-warning">Your role is read-only, so tokens cannot log until an admin grants write access.</p>
          {/if}
          <form class="token-form" onsubmit={createToken}>
            <input
              class="token-input"
              aria-label="Token name"
              placeholder="Token name, e.g. gpu-cluster"
              maxlength="64"
              bind:value={newTokenName}
              autocomplete="off"
            />
            <button class="token-btn token-btn-primary" type="submit" disabled={creatingToken}>
              {creatingToken ? "Creating…" : "Create token"}
            </button>
          </form>
          {#if freshToken}
            <div class="fresh-token" role="status">
              <p>Copy <strong>{freshToken.name}</strong> now. It will not be shown again.</p>
              <CodeSnippet code={freshToken.token} />
            </div>
          {/if}
          <p class="section-desc token-usage-label">Set these on every node that runs training:</p>
          <CodeSnippet code={usageSnippet} />
          {#if apiTokenError}
            <p class="token-error" role="alert">{apiTokenError}</p>
          {/if}
          {#if apiTokens.length > 0}
            <div class="storage-table-wrap">
              <table class="storage-table token-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Token</th>
                    <th>Created (UTC)</th>
                    <th>Last used (UTC)</th>
                    <th><span class="visually-hidden">Actions</span></th>
                  </tr>
                </thead>
                <tbody>
                  {#each apiTokens as token (token.id)}
                    <tr>
                      <td>{token.name}</td>
                      <td><code>{maskedToken(token)}</code></td>
                      <td>{token.created_at}</td>
                      <td>{token.last_used_at ?? "Never"}</td>
                      <td class="num">
                        <button
                          class="token-btn token-btn-danger"
                          disabled={revokingTokenId === token.id}
                          onclick={() => revokeToken(token)}
                        >
                          {revokingTokenId === token.id ? "Revoking…" : "Revoke"}
                        </button>
                      </td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          {:else}
            <p class="storage-empty">No personal tokens yet.</p>
          {/if}
        </section>
      {/if}

      <section class="settings-section">
        <h3 class="section-title">Appearance</h3>
        <p class="section-desc">Choose how the dashboard looks to you.</p>
        <div class="theme-switcher">
          {#each [
            { value: "system", label: "System" },
            { value: "light", label: "Light" },
            { value: "dark", label: "Dark" },
          ] as opt}
            <button
              class="theme-option"
              class:selected={themeChoice === opt.value}
              onclick={() => switchTheme(opt.value)}
            >
              {#if opt.value === "system"}
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <rect x="2" y="3" width="20" height="14" rx="2" />
                  <path d="M8 21h8" />
                  <path d="M12 17v4" />
                </svg>
              {:else if opt.value === "light"}
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <circle cx="12" cy="12" r="4" />
                  <path d="M12 2v2" />
                  <path d="M12 20v2" />
                  <path d="M4.93 4.93l1.41 1.41" />
                  <path d="M17.66 17.66l1.41 1.41" />
                  <path d="M2 12h2" />
                  <path d="M20 12h2" />
                  <path d="M6.34 17.66l-1.41 1.41" />
                  <path d="M19.07 4.93l-1.41 1.41" />
                </svg>
              {:else}
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
                </svg>
              {/if}
              {opt.label}
            </button>
          {/each}
        </div>
      </section>

      <section class="settings-section">
        <h3 class="section-title">CLI Reference</h3>
        <p class="section-desc">
          Common Trackio CLI commands.
          {#if spaceId}
            Connected to <strong>{spaceId}</strong> — remote commands include <code>--space</code> automatically.
          {/if}
        </p>
        {#if projects.length > 0}
          <div class="project-selector">
            <label class="selector-label" for="cli-project">Project</label>
            <select
              id="cli-project"
              class="ui-select selector-select"
              bind:value={cliProject}
            >
              {#each projects as p}
                <option value={p}>{p}</option>
              {/each}
            </select>
          </div>
        {/if}
        <div class="commands-table">
          {#each commands as cmd, i}
            <div class="command-row">
              <span class="command-label">{cmd.title}</span>
              <div class="command-value">
                <code>{cmd.cmd}</code>
                <button
                  class="copy-btn"
                  class:copied={copiedIdx === i}
                  onclick={() => copyCommand(cmd.cmd, i)}
                  title="Copy"
                >
                  {#if copiedIdx === i}
                    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M3.5 8.5l3 3 6-7" />
                    </svg>
                  {:else}
                    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                      <rect x="5" y="5" width="8" height="8" rx="1.5" />
                      <path d="M11 5V3.5A1.5 1.5 0 009.5 2h-6A1.5 1.5 0 002 3.5v6A1.5 1.5 0 003.5 11H5" />
                    </svg>
                  {/if}
                </button>
              </div>
            </div>
          {/each}
        </div>
      </section>
    </div>

    <div class="col col-right">
      <section class="settings-section">
        <h3 class="section-title">Agent Skills</h3>
        <p class="section-desc">Install Trackio as a skill in your AI coding agent to query experiments with natural language.</p>

        <div class="agent-tabs">
          {#each agents as agent}
            <button
              class="agent-tab"
              class:active={selectedAgent === agent.id}
              onclick={() => { selectedAgent = agent.id; }}
            >
              {agent.label}
            </button>
          {/each}
        </div>

        <div class="agent-panel">
          <div class="install-block">
            <span class="install-label">Run in Terminal to Install:</span>
            <div class="install-cmd">
              <code>{agentInstallCmd}</code>
              <button
                class="copy-btn"
                class:copied={agentCopied}
                onclick={() => copyText(agentInstallCmd, "agent")}
                title="Copy"
              >
                {#if agentCopied}
                  <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M3.5 8.5l3 3 6-7" />
                  </svg>
                {:else}
                  <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="5" y="5" width="8" height="8" rx="1.5" />
                    <path d="M11 5V3.5A1.5 1.5 0 009.5 2h-6A1.5 1.5 0 002 3.5v6A1.5 1.5 0 003.5 11H5" />
                  </svg>
                {/if}
              </button>
            </div>
          </div>

          <div class="example-block">
            <div class="example-header">
              <span class="example-label">Example prompt</span>
              <button
                class="copy-btn"
                class:copied={exampleCopied}
                onclick={() => copyText(agentExample, "example")}
                title="Copy"
              >
                {#if exampleCopied}
                  <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M3.5 8.5l3 3 6-7" />
                  </svg>
                {:else}
                  <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="5" y="5" width="8" height="8" rx="1.5" />
                    <path d="M11 5V3.5A1.5 1.5 0 009.5 2h-6A1.5 1.5 0 002 3.5v6A1.5 1.5 0 003.5 11H5" />
                  </svg>
                {/if}
              </button>
            </div>
            <p class="example-text">{agentExample}</p>
          </div>
        </div>
      </section>
    </div>
  </div>

  {#if storage || storageLoading || storageError}
    <section class="settings-section storage-section">
      <div class="storage-heading">
        <div>
          <h3 class="section-title">Storage</h3>
          <p class="section-desc">
            Disk used by each project under <code>{storage?.trackio_dir ?? "…"}</code>.
            {#if disk}
              <span class:disk-low={disk.low}>
                {formatBytes(disk.free)} free of {formatBytes(disk.total)} ({disk.usedPercent}% of the disk used){disk.low ? " — running low" : ""}.
              </span>
            {/if}
          </p>
        </div>
        <button class="storage-refresh" onclick={loadStorage} disabled={storageLoading}>
          {storageLoading ? "Measuring…" : "Refresh"}
        </button>
      </div>
      {#if storageError}
        <p class="storage-empty">Could not measure storage: {storageError}</p>
      {:else if storage && storageTable.rows.length === 0}
        <p class="storage-empty">No projects yet.</p>
      {:else if storage}
        <div class="storage-table-wrap">
          <table class="storage-table">
            <thead>
              <tr>
                <th>Project</th>
                {#each STORAGE_CATEGORIES as category}
                  <th class="num">{category.label}</th>
                {/each}
                <th class="num">Total</th>
              </tr>
            </thead>
            <tbody>
              {#each storageTable.rows as row}
                <tr class:selected={row.selected}>
                  <td class="project-cell">{row.project}</td>
                  {#each row.cells as bytes}
                    <td class="num" class:zero={!bytes}>{formatBytes(bytes)}</td>
                  {/each}
                  <td class="num total">{formatBytes(row.total)}</td>
                </tr>
              {/each}
            </tbody>
            {#if storageTable.rows.length > 1}
              <tfoot>
                <tr>
                  <td>All projects</td>
                  {#each storageTable.totals as bytes}
                    <td class="num">{formatBytes(bytes)}</td>
                  {/each}
                  <td class="num total">{formatBytes(storageTable.total)}</td>
                </tr>
              </tfoot>
            {/if}
          </table>
        </div>
        <p class="storage-tip">
          Files are copied in full on every <code>trackio.save()</code>; artifacts store each distinct
          file once, but every changed checkpoint is a new full copy. Keep large data where it lives
          with <code>artifact.add_reference(...)</code>, keep only the newest version with
          <code>log_artifact(..., overwrite=True)</code>, and reclaim a project's space with
          <code>trackio.delete_project()</code>.
        </p>
      {/if}
    </section>
  {/if}
</div>

<style>
  .settings-page {
    min-width: 0;
    box-sizing: border-box;
    padding: 28px;
    overflow-y: auto;
    flex: 1;
  }
  .two-col {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    gap: 24px;
    align-items: start;
  }
  @media (max-width: 900px) {
    .two-col {
      grid-template-columns: minmax(0, 1fr);
    }
  }
  .col { min-width: 0; }
  .storage-heading {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
  }
  .storage-refresh {
    flex-shrink: 0;
    padding: 5px 10px;
    border: 1px solid var(--border-color-primary, #e5e7eb);
    border-radius: var(--radius-md, 6px);
    background: var(--background-fill-primary, white);
    color: var(--body-text-color, #1f2937);
    font: inherit;
    font-size: 12px;
    cursor: pointer;
  }
  .storage-refresh:disabled {
    cursor: wait;
    opacity: 0.6;
  }
  .disk-low {
    color: var(--status-danger);
    font-weight: 600;
  }
  .storage-table-wrap {
    overflow-x: auto;
    border: 1px solid var(--border-color-primary, #e5e7eb);
    border-radius: var(--radius-lg, 8px);
  }
  .storage-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
  }
  .storage-table th,
  .storage-table td {
    padding: 8px 12px;
    border-bottom: 1px solid var(--border-color-primary, #e5e7eb);
    text-align: left;
    white-space: nowrap;
  }
  .storage-table th {
    background: var(--background-fill-secondary, #f9fafb);
    color: var(--body-text-color-subdued, #6b7280);
    font-weight: 600;
  }
  .storage-table .num {
    text-align: right;
    font-variant-numeric: tabular-nums;
  }
  .storage-table td.zero {
    color: var(--body-text-color-subdued, #9ca3af);
  }
  .storage-table td.total,
  .storage-table tfoot td {
    font-weight: 600;
  }
  .storage-table tbody tr:last-child td {
    border-bottom: none;
  }
  .storage-table tfoot td {
    border-top: 1px solid var(--border-color-primary, #e5e7eb);
    border-bottom: none;
  }
  .storage-table tr.selected .project-cell {
    color: var(--color-accent, #f97316);
    font-weight: 600;
  }
  .storage-empty,
  .storage-tip {
    margin: 10px 0 0;
    color: var(--body-text-color-subdued, #6b7280);
    font-size: 12px;
    line-height: 1.55;
  }
  .storage-tip code {
    padding: 1px 4px;
    border-radius: var(--radius-sm, 3px);
    background: var(--background-fill-secondary, #f3f4f6);
    font-size: 11px;
  }
  .token-form {
    display: flex;
    gap: 8px;
    margin-bottom: 4px;
  }
  .token-input {
    flex: 1;
    min-width: 0;
    padding: 7px 10px;
    border: 1px solid var(--border-color-primary, #e5e7eb);
    border-radius: var(--radius-md, 6px);
    background: var(--input-background-fill, white);
    color: var(--body-text-color, #1f2937);
    font: inherit;
    font-size: 13px;
  }
  .token-btn {
    flex-shrink: 0;
    padding: 6px 12px;
    border: 1px solid var(--border-color-primary, #e5e7eb);
    border-radius: var(--radius-md, 6px);
    background: var(--background-fill-primary, white);
    color: var(--body-text-color, #1f2937);
    font: inherit;
    font-size: 12px;
    font-weight: 500;
    cursor: pointer;
  }
  .token-btn-primary {
    border-color: var(--primary-600, #ea580c);
    background: var(--primary-600, #ea580c);
    color: white;
    font-weight: 600;
  }
  .token-btn-danger {
    color: var(--status-danger);
  }
  .token-btn:disabled {
    cursor: not-allowed;
    opacity: 0.6;
  }
  .fresh-token {
    margin-top: 14px;
    padding: 12px 14px 2px;
    border: 1px solid color-mix(in srgb, var(--primary-600, #ea580c) 40%, transparent);
    border-radius: var(--radius-lg, 8px);
    background: color-mix(in srgb, var(--primary-600, #ea580c) 6%, transparent);
  }
  .fresh-token p {
    margin: 0;
    font-size: 12px;
    color: var(--body-text-color, #1f2937);
  }
  .token-usage-label {
    margin: 16px 0 0;
  }
  .token-warning,
  .token-error {
    margin: 0 0 12px;
    font-size: 12px;
    color: var(--status-danger);
  }
  .token-table code {
    font-size: 11px;
  }
  .visually-hidden {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
  }
  .settings-section {
    margin-bottom: 24px;
    padding: 22px;
    border: 1px solid var(--border-color-primary, #e5e7eb);
    border-radius: 12px;
    background: var(--background-fill-primary, white);
  }
  .section-title {
    color: var(--body-text-color, #1f2937);
    font-size: 15px;
    font-weight: 600;
    margin: 0 0 4px;
  }
  .section-desc {
    color: var(--body-text-color-subdued, #6b7280);
    font-size: var(--text-sm, 12px);
    margin: 0 0 12px;
    line-height: 1.5;
  }
  .section-desc code {
    background: var(--background-fill-secondary, #f3f4f6);
    padding: 1px 5px;
    border-radius: var(--radius-sm, 3px);
    font-size: 11px;
  }
  .section-desc strong {
    color: var(--color-accent, #f97316);
  }

  .theme-switcher {
    display: inline-flex;
    border: 1px solid var(--border-color-primary, #e5e7eb);
    border-radius: var(--radius-lg, 8px);
    overflow: hidden;
  }
  .theme-option {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 8px 20px;
    border: none;
    background: var(--background-fill-primary, white);
    color: var(--body-text-color-subdued, #6b7280);
    font-size: var(--text-md, 14px);
    cursor: pointer;
    transition: all 0.15s;
    border-right: 1px solid var(--border-color-primary, #e5e7eb);
  }
  .theme-option:last-child {
    border-right: none;
  }
  .theme-option:hover {
    color: var(--body-text-color, #1f2937);
    background: var(--background-fill-secondary, #f9fafb);
  }
  .theme-option.selected {
    background: var(--color-accent, #f97316);
    color: white;
    font-weight: 500;
  }

  .project-selector {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 12px;
  }
  .selector-label {
    font-size: 13px;
    color: var(--body-text-color-subdued, #6b7280);
    flex-shrink: 0;
  }
  .selector-select {
    min-width: 160px;
  }

  .commands-table {
    border: 1px solid var(--border-color-primary, #e5e7eb);
    border-radius: var(--radius-lg, 8px);
    overflow: hidden;
  }
  .command-row {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 10px 14px;
    border-bottom: 1px solid var(--border-color-primary, #e5e7eb);
  }
  .command-row:last-child {
    border-bottom: none;
  }
  .command-label {
    width: 180px;
    flex-shrink: 0;
    font-size: var(--text-sm, 12px);
    color: var(--body-text-color-subdued, #6b7280);
  }
  .command-value {
    flex: 1;
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
  }
  .command-value code {
    flex: 1;
    font-family: "SFMono-Regular", "Consolas", "Liberation Mono", "Menlo", monospace;
    font-size: 12px;
    color: var(--body-text-color, #1f2937);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .copy-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 26px;
    height: 26px;
    flex-shrink: 0;
    border: none;
    background: none;
    border-radius: var(--radius-md, 4px);
    color: var(--body-text-color-subdued, #6b7280);
    cursor: pointer;
    transition: background-color 0.15s, color 0.15s;
  }
  .copy-btn:hover {
    background: var(--background-fill-secondary, #f3f4f6);
    color: var(--body-text-color, #1f2937);
  }
  .copy-btn.copied {
    color: var(--color-accent, #f97316);
  }

  .agent-tabs {
    overflow-x: auto;
    display: flex;
    border-bottom: 1px solid var(--border-color-primary, #e5e7eb);
    gap: 0;
    margin-bottom: 0;
  }
  .agent-tab {
    padding: 8px 16px;
    border: none;
    background: none;
    color: var(--body-text-color-subdued, #6b7280);
    font-size: var(--text-sm, 12px);
    cursor: pointer;
    border-bottom: 2px solid transparent;
    transition: all 0.15s;
    white-space: nowrap;
  }
  .agent-tab:hover {
    color: var(--body-text-color, #1f2937);
  }
  .agent-tab.active {
    color: var(--color-accent, #f97316);
    border-bottom-color: var(--color-accent, #f97316);
    font-weight: 500;
  }

  .agent-panel {
    border: 1px solid var(--border-color-primary, #e5e7eb);
    border-top: none;
    border-radius: 0 0 var(--radius-lg, 8px) var(--radius-lg, 8px);
    padding: 16px;
  }

  .install-block {
    margin-bottom: 16px;
  }
  .install-label {
    display: block;
    font-size: 11px;
    font-weight: 500;
    color: var(--body-text-color-subdued, #6b7280);
    text-transform: uppercase;
    letter-spacing: 0.04em;
    margin-bottom: 6px;
  }
  .install-cmd {
    display: flex;
    align-items: center;
    gap: 8px;
    background: var(--background-fill-secondary, #f3f4f6);
    border-radius: var(--radius-md, 4px);
    padding: 8px 10px;
  }
  .install-cmd code {
    flex: 1;
    font-family: "SFMono-Regular", "Consolas", "Liberation Mono", "Menlo", monospace;
    font-size: 12px;
    color: var(--body-text-color, #1f2937);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .example-block {
    background: var(--background-fill-secondary, #f9fafb);
    border: 1px solid var(--border-color-primary, #e5e7eb);
    border-radius: var(--radius-md, 4px);
    padding: 12px;
  }
  .example-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 8px;
  }
  .example-label {
    font-size: 11px;
    font-weight: 500;
    color: var(--body-text-color-subdued, #6b7280);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .example-text {
    margin: 0;
    font-size: var(--text-sm, 12px);
    color: var(--body-text-color, #1f2937);
    line-height: 1.6;
    font-style: italic;
  }
  @media (max-width: 700px) {
    .settings-page { padding: 20px 16px; }
    .settings-section { padding: 18px; }
    .theme-switcher { display: flex; }
    .theme-option { flex: 1; justify-content: center; padding: 8px; }
    .project-selector { flex-wrap: wrap; }
    .selector-select { min-width: 0; max-width: 100%; }
    .command-row { flex-direction: column; align-items: stretch; gap: 6px; }
    .command-label { width: auto; }
    .command-value code { white-space: normal; overflow-wrap: anywhere; }
    .agent-tab { padding: 8px 12px; }

  }
</style>
