<script>
  import { onMount } from "svelte";
  import {
    adminCreateUser,
    adminGetAuthSettings,
    adminResetPassword,
    adminSetAuthSettings,
    adminSetRole,
    adminTestOidc,
    getAdminUsers,
    revokeUserSessions,
  } from "../lib/api.js";

  let { isAdmin = false } = $props();

  let loading = $state(true);
  let error = $state(null);
  let users = $state([]);
  let writeTokenProjects = $state([]);
  let authRequired = $state(false);
  let oidcEnabled = $state(false);
  let expandedSub = $state(null);
  let revoking = $state(null);

  async function refresh() {
    loading = true;
    error = null;
    try {
      const data = await getAdminUsers();
      users = data.users ?? [];
      writeTokenProjects = data.write_token_projects ?? [];
      authRequired = !!data.auth_required;
      oidcEnabled = !!data.oidc_enabled;
    } catch (e) {
      error = e?.message ?? String(e);
    } finally {
      loading = false;
    }
  }

  onMount(() => {
    refresh();
    loadAuthSettings();
  });

  async function revoke(sub) {
    revoking = sub;
    try {
      await revokeUserSessions(sub);
      await refresh();
    } catch (e) {
      error = e?.message ?? String(e);
    } finally {
      revoking = null;
    }
  }

  function toggleExpand(sub) {
    expandedSub = expandedSub === sub ? null : sub;
  }

  async function changeRole(sub, role) {
    try {
      await adminSetRole(sub, role);
      await refresh();
    } catch (e) {
      error = e?.message ?? String(e);
    }
  }

  function currentRole(user) {
    if (user.role_override) return user.role_override;
    return "default";
  }

  let authSettings = $state(null);
  let settingsSecret = $state("");
  let settingsSaving = $state(false);
  let settingsMessage = $state(null);
  let testMessage = $state(null);

  async function loadAuthSettings() {
    try {
      authSettings = await adminGetAuthSettings();
      settingsSecret = "";
    } catch {
      authSettings = null;
    }
  }

  async function saveAuthSettings(e) {
    e.preventDefault();
    settingsSaving = true;
    settingsMessage = null;
    try {
      authSettings = await adminSetAuthSettings({
        ...authSettings,
        client_secret: settingsSecret,
      });
      settingsSecret = "";
      oidcEnabled = !!authSettings.oidc_active;
      authRequired = !!authSettings.auth_required_active;
      settingsMessage = "Settings saved.";
    } catch (err) {
      settingsMessage = err?.message ?? String(err);
    } finally {
      settingsSaving = false;
    }
  }

  async function testOidc() {
    testMessage = "Testing…";
    try {
      const result = await adminTestOidc(authSettings?.issuer ?? "");
      testMessage = `Discovery OK: ${result.authorization_endpoint}`;
    } catch (err) {
      testMessage = err?.message ?? String(err);
    }
  }

  let newUsername = $state("");
  let newPassword = $state("");
  let newRole = $state("write");
  let creating = $state(false);
  let showCreateUser = $state(false);
  let authExpanded = $state(false);
  let createMessage = $state(null);

  function toggleCreateUser() {
    showCreateUser = !showCreateUser;
    createMessage = null;
    if (!showCreateUser) {
      newUsername = "";
      newPassword = "";
      newRole = "write";
    }
  }

  async function createUser(e) {
    e.preventDefault();
    creating = true;
    createMessage = null;
    try {
      await adminCreateUser(newUsername, newPassword, newRole);
      createMessage = `Created local account "${newUsername}".`;
      newUsername = "";
      newPassword = "";
      newRole = "write";
      showCreateUser = false;
      await refresh();
    } catch (err) {
      createMessage = err?.message ?? String(err);
    } finally {
      creating = false;
    }
  }

  async function resetPassword(sub) {
    const password = window.prompt(
      "New password (min 8 characters) for " + sub.replace("local:", "") + ":",
    );
    if (!password) return;
    try {
      await adminResetPassword(sub, password);
      error = null;
    } catch (err) {
      error = err?.message ?? String(err);
    }
  }

  function displayName(user) {
    return user.name || user.username || user.email || user.sub;
  }

  function actionsSummary(project) {
    return Object.entries(project.actions ?? {})
      .map(([action, count]) => `${action} ×${count}`)
      .join(", ");
  }
</script>

<div class="admin-page">
  <header class="page-header">
    <div>
      <p class="eyebrow">Administration</p>
      <h2>Users & Access</h2>
      <p class="subtitle">Manage accounts, sign-in options, and project access.</p>
    </div>
    <span class="badge badge-admin">Admin workspace</span>
  </header>

  {#if isAdmin && !loading && !error}
    <div class="overview" aria-label="Access overview">
      <div><span class="stat-label">Registered users</span><strong>{users.length}</strong></div>
      <div><span class="stat-label">Active sessions</span><strong>{users.reduce((total, user) => total + (user.active_sessions ?? 0), 0)}</strong></div>
      <div><span class="stat-label">Dashboard access</span><strong>{authRequired ? "Sign-in required" : "Public"}</strong></div>
      <div><span class="stat-label">OIDC sign-in</span><strong><span class="status-dot" class:enabled={oidcEnabled}></span>{oidcEnabled ? "Enabled" : "Not configured"}</strong></div>
    </div>
  {/if}

  {#if error}
    <p class="error" role="alert">{error}</p>
  {/if}

  {#if loading}
    <p class="empty-state" role="status">Loading users and access settings…</p>
  {:else if !isAdmin}
    <p class="error">Admin access is required to view this page.</p>
  {:else}

    <section>
      <div class="section-header">
        <div>
          <h3>Users <span class="badge badge-read">{users.length}</span></h3>
          <p class="muted">Manage roles and sessions. Select a user to view activity.</p>
        </div>
        <button class="create-btn" type="button" aria-expanded={showCreateUser} aria-controls="create-user-panel" disabled={creating} onclick={toggleCreateUser}>
          {showCreateUser ? "Cancel" : "+ Add user"}
        </button>
      </div>
      <div id="create-user-panel" class="create-panel" hidden={!showCreateUser}>
        <h4>Create local account</h4>
        <p class="muted">
          Password-based account managed by this server (independent of the
          OIDC provider). The user signs in on the
          <span class="mono">/login</span> page.
        </p>
        <form class="create-form" onsubmit={createUser}>
          <label>Username
            <input
              required
              placeholder="e.g. alex"
              bind:value={newUsername}
              autocomplete="off"
            />
          </label>
          <label>Password
            <input
              required
              minlength="8"
              placeholder="At least 8 characters"
              type="password"
              bind:value={newPassword}
              autocomplete="new-password"
            />
          </label>
          <label>Role
            <select class="role-select" bind:value={newRole}>
              <option value="admin">admin</option>
              <option value="write">write</option>
              <option value="read">read-only</option>
            </select>
          </label>
          <button class="create-btn" type="submit" disabled={creating}>
            {creating ? "Creating…" : "Create user"}
          </button>
        </form>
      </div>
      {#if createMessage}
        <p class="feedback create-feedback" role="status">{createMessage}</p>
      {/if}
      {#if users.length === 0}
        <p class="muted">
          No users yet. The first admin account is registered on the
          <span class="mono">/setup</span> page.
        </p>
      {:else}
        <div class="table-scroll" role="region" aria-label="Users">
          <table class="admin-table">
            <thead>
              <tr>
                <th>User</th>
                <th>Role</th>
                <th>Last login</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {#each users as user (user.sub)}
                <tr class="user-row" class:expanded={expandedSub === user.sub}>
                  <td class="name-cell">
                    <button class="user-toggle" aria-expanded={expandedSub === user.sub} onclick={() => toggleExpand(user.sub)}>
                      <span class="chevron" aria-hidden="true">{expandedSub === user.sub ? "▾" : "▸"}</span>
                      {displayName(user)}
                    </button>
                    {#if user.auth_type === "local"}
                      <span class="badge badge-type">local</span>
                    {/if}
                    {#if user.email && user.email !== displayName(user)}
                      <span class="user-email">{user.email}</span>
                    {/if}
                  </td>
                  <td>
                    <select
                      class="role-select"
                      aria-label={`Role for ${displayName(user)}`}
                      value={currentRole(user)}
                      onclick={(e) => e.stopPropagation()}
                      onchange={(e) => changeRole(user.sub, e.target.value)}
                    >
                      <option value="default">Default{currentRole(user) === "default" ? ` (${user.is_admin ? "admin" : user.can_write ? "write" : "read-only"})` : ""}</option>
                      <option value="admin">admin</option>
                      <option value="write">write</option>
                      <option value="read">read-only</option>
                    </select>
                  </td>
                  <td class="muted">{user.last_login ?? "—"}</td>
                  <td class="actions-cell">
                    {#if user.auth_type === "local"}
                      <button
                        class="secondary-btn"
                        onclick={(e) => {
                          e.stopPropagation();
                          resetPassword(user.sub);
                        }}
                      >
                        Reset password
                      </button>
                    {/if}
                    {#if user.active_sessions > 0}
                      <button
                        class="revoke-btn"
                        disabled={revoking === user.sub}
                        onclick={(e) => {
                          e.stopPropagation();
                          revoke(user.sub);
                        }}
                      >
                        {revoking === user.sub ? "Revoking…" : "Sign out"}
                      </button>
                    {/if}
                  </td>
                </tr>
                {#if expandedSub === user.sub}
                  <tr class="detail-row">
                    <td colspan="4">
                      <div class="detail">
                        <dl class="activity-stats">
                          <div><dt>Logins</dt><dd>{user.login_count ?? 0}</dd></div>
                          <div><dt>Active sessions</dt><dd>{user.active_sessions ?? 0}</dd></div>
                          <div><dt>Projects</dt><dd>{user.projects.length}</dd></div>
                        </dl>
                        <p class="muted mono">sub: {user.sub}</p>
                        {#if user.groups?.length}
                          <p class="muted">Groups: {user.groups.join(", ")}</p>
                        {/if}
                        {#if user.projects.length === 0}
                          <p class="muted">No write activity recorded.</p>
                        {:else}
                          <table class="project-table">
                            <thead>
                              <tr>
                                <th>Project</th>
                                <th>Activity</th>
                                <th>First</th>
                                <th>Last</th>
                              </tr>
                            </thead>
                            <tbody>
                              {#each user.projects as project (project.project)}
                                <tr>
                                  <td>{project.project}</td>
                                  <td class="muted">{actionsSummary(project)}</td>
                                  <td class="muted">{project.first_seen ?? "—"}</td>
                                  <td class="muted">{project.last_seen ?? "—"}</td>
                                </tr>
                              {/each}
                            </tbody>
                          </table>
                        {/if}
                      </div>
                    </td>
                  </tr>
                {/if}
              {/each}
            </tbody>
          </table>
        </div>
      {/if}
    </section>

    {#if authSettings}
      <details class="auth-settings" bind:open={authExpanded}>
        <summary>Authentication settings <span class="summary-hint">OIDC and dashboard sign-in</span></summary>
        <div class="auth-content">
        <p class="muted">
          OIDC sign-in becomes available on the login page once enabled and
          saved here. Saved settings take precedence over
          <span class="mono">TRACKIO_OIDC_*</span> environment variables
          {#if authSettings.source === "env"}(currently using environment
          fallback){/if}.
        </p>
        <form class="settings-form" onsubmit={saveAuthSettings}>
          <label class="toggle">
            <input type="checkbox" bind:checked={authSettings.oidc_enabled} />
            Enable OIDC sign-in
            {#if authSettings.oidc_active}
              <span class="badge badge-write">active</span>
            {:else}
              <span class="badge badge-read">inactive</span>
            {/if}
          </label>
          <fieldset>
            <legend>Identity provider</legend>
            <div class="settings-grid">
              <label>Issuer URL
                <input bind:value={authSettings.issuer} placeholder="https://idp.example.com/realms/main" />
              </label>
              <label>Client ID
                <input bind:value={authSettings.client_id} />
              </label>
              <label>Client secret
                <input
                  type="password"
                  bind:value={settingsSecret}
                  placeholder={authSettings.client_secret_set ? "(unchanged)" : ""}
                  autocomplete="new-password"
                />
              </label>
              <label>Scopes
                <input bind:value={authSettings.scopes} placeholder="openid profile email" />
              </label>
              <label>Groups claim
                <input bind:value={authSettings.groups_claim} placeholder="groups" />
              </label>
            </div>
          </fieldset>
          <label class="toggle">
            <input type="checkbox" bind:checked={authSettings.auth_required} />
            Require sign-in for the whole dashboard (write-token clients are
            exempt)
            {#if authSettings.auth_required_active && !authSettings.auth_required}
              <span class="badge badge-read">forced on by env</span>
            {/if}
          </label>
          <div class="settings-actions">
            <button class="create-btn" type="submit" disabled={settingsSaving}>
              {settingsSaving ? "Saving…" : "Save settings"}
            </button>
            <button class="secondary-btn" type="button" onclick={testOidc}>
              Test discovery
            </button>
            {#if settingsMessage}<span class="feedback" role="status">{settingsMessage}</span>{/if}
            {#if testMessage}<span class="feedback" role="status">{testMessage}</span>{/if}
          </div>
        </form>
        </div>
      </details>
    {/if}


    <section>
      <h3>Write-token clients</h3>
      <p class="muted">
        Projects written by scripts authenticating with the server write token
        (no user identity).
      </p>
      {#if writeTokenProjects.length === 0}
        <p class="empty-state">No write-token activity recorded yet.</p>
      {:else}
        <div class="table-scroll" role="region" aria-label="Write-token activity">
          <table class="project-table standalone">
            <thead>
              <tr>
                <th>Project</th>
                <th>Activity</th>
                <th>First</th>
                <th>Last</th>
              </tr>
            </thead>
            <tbody>
              {#each writeTokenProjects as project (project.project)}
                <tr>
                  <td>{project.project}</td>
                  <td class="muted">{actionsSummary(project)}</td>
                  <td class="muted">{project.first_seen ?? "—"}</td>
                  <td class="muted">{project.last_seen ?? "—"}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {/if}
    </section>

    <p class="hint">
      Activity timestamps are UTC. High-frequency logging is aggregated (one
      count per minute per project). The Role column takes effect
      immediately, including for active sessions. Default follows the server’s
      configured access rules; the role in parentheses shows current access.
    </p>
  {/if}
</div>

<style>
  .admin-page {
    --surface: var(--background-fill-primary, white);
    --subtle: var(--background-fill-secondary, #f9fafb);
    --line: var(--border-color-primary, #e5e7eb);
    --text: var(--body-text-color, #1f2937);
    --muted: var(--body-text-color-subdued, #6b7280);
    box-sizing: border-box;
    width: 100%;
    max-width: 1440px;
    margin: 0 auto;
    padding: 32px;
    overflow-y: auto;
    color: var(--text);
    font-size: 13px;
    line-height: 1.6;
  }
  .page-header { display: flex; justify-content: space-between; align-items: center; gap: 20px; margin-bottom: 24px; }
  .eyebrow { margin: 0 0 4px; color: var(--muted); font-size: 10px; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; }
  h2 { margin: 0; font-size: 26px; font-weight: 650; letter-spacing: -.035em; line-height: 1.3; }
  h3 { display: flex; align-items: center; gap: 8px; margin: 0 0 6px; font-size: 16px; font-weight: 600; letter-spacing: -.015em; }
  .subtitle { margin: 6px 0 0; color: var(--muted); }
  .overview { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); margin-bottom: 24px; border: 1px solid var(--line); border-radius: 12px; background: var(--subtle); }
  .overview > div { padding: 18px 22px; }
  .overview > div + div { border-left: 1px solid var(--line); }
  .stat-label { display: block; color: var(--muted); font-size: 12px; margin-bottom: 6px; }
  .overview strong { display: flex; align-items: center; gap: 8px; font-size: 18px; font-weight: 600; line-height: 1.4; }
  .status-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--muted); flex-shrink: 0; }
  .status-dot.enabled { background: #22c55e; }
  section { padding: 24px; margin-bottom: 20px; border: 1px solid var(--line); border-radius: 12px; background: var(--surface); }
  .muted { color: var(--muted); font-size: 13px; }
  section > .muted { margin: 0 0 20px; max-width: 850px; }
  .mono { font-family: var(--font-mono, monospace); font-size: 12px; overflow-wrap: anywhere; }
  .error { color: #dc2626; padding: 12px 16px; border: 1px solid currentColor; border-radius: 8px; overflow-wrap: anywhere; }
  .empty-state { padding: 28px 20px; margin: 16px 0 0; text-align: center; color: var(--muted); border: 1px dashed var(--line); border-radius: 8px; background: var(--subtle); }
  .settings-form { display: flex; flex-direction: column; gap: 22px; }
  fieldset { min-width: 0; margin: 0; padding: 0; border: 0; }
  legend { padding: 0; margin-bottom: 12px; font-weight: 600; }
  .settings-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 18px; }
  .settings-grid label, .create-form label { display: flex; flex-direction: column; gap: 7px; min-width: 0; font-size: 12px; font-weight: 500; }
  .toggle { display: flex; align-items: center; gap: 10px; padding: 14px 16px; border: 1px solid var(--line); border-radius: 8px; background: var(--subtle); cursor: pointer; }
  .toggle input { width: 16px; height: 16px; flex-shrink: 0; accent-color: var(--color-accent, #f97316); }
  .toggle .badge { margin-left: auto; }
  .settings-grid input, .create-form input, .role-select { box-sizing: border-box; width: 100%; min-width: 0; min-height: 38px; padding: 8px 11px; border: 1px solid var(--line); border-radius: 7px; background: var(--input-background-fill, white); color: var(--text); font: inherit; font-size: 13px; }
  input::placeholder { color: var(--muted); opacity: .75; }
  button, input, select { transition: border-color .15s, background-color .15s; }
  button:focus-visible, input:focus-visible, select:focus-visible { outline: 2px solid var(--color-accent, #f97316); outline-offset: 3px; }
  .settings-actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding-top: 18px; border-top: 1px solid var(--line); }
  .create-form { display: grid; grid-template-columns: 1fr 1fr minmax(120px, .6fr) auto; gap: 14px; align-items: end; }
  .create-btn, .secondary-btn, .revoke-btn { min-height: 36px; padding: 7px 13px; border: 1px solid var(--line); border-radius: 7px; background: var(--surface); color: var(--text); font: inherit; font-size: 12px; font-weight: 500; cursor: pointer; }
  .create-btn { background: var(--text); color: var(--surface); border-color: var(--text); font-weight: 600; min-height: 38px; }
  .create-btn:hover:not(:disabled) { opacity: .85; }
  .secondary-btn:hover:not(:disabled) { background: var(--subtle); }
  .revoke-btn { color: #dc2626; }
  .revoke-btn:hover:not(:disabled) { border-color: currentColor; }
  button:disabled { opacity: .5; cursor: not-allowed; }
  .feedback { flex-basis: 100%; margin: 0; padding: 10px 12px; border-radius: 6px; background: var(--subtle); color: var(--muted); overflow-wrap: anywhere; }
  .section-header { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 16px; margin-bottom: 20px; }
  .section-header p { margin: 0; }
  .create-panel { padding: 18px; margin-bottom: 20px; border: 1px solid var(--line); border-radius: 8px; background: var(--subtle); }
  .create-panel h4 { margin: 0; font-size: 14px; font-weight: 600; }
  .create-panel p { margin: 4px 0 16px; }
  .create-feedback { margin-bottom: 16px; }
  .user-email { display: block; margin-left: 18px; color: var(--muted); font-size: 12px; overflow-wrap: anywhere; }
  .activity-stats { display: flex; flex-wrap: wrap; gap: 16px 36px; margin: 0 0 16px; }
  .activity-stats dt { font-size: 11px; color: var(--muted); }
  .activity-stats dd { margin: 2px 0 0; font-size: 16px; font-weight: 600; }
  .auth-settings { margin-bottom: 20px; border: 1px solid var(--line); border-radius: 12px; background: var(--surface); }
  summary { padding: 20px 24px; cursor: pointer; font-size: 15px; font-weight: 600; }
  summary:focus-visible { outline: 2px solid var(--color-accent, #f97316); outline-offset: 3px; border-radius: 12px; }
  .summary-hint { margin-left: 12px; font-size: 12px; font-weight: 400; color: var(--muted); }
  .auth-content { padding: 0 24px 24px; }
  .auth-content > p { margin: 0 0 20px; }
  .table-scroll { max-width: 100%; overflow-x: auto; border: 1px solid var(--line); border-radius: 8px; }
  .admin-table, .project-table { width: 100%; border-collapse: collapse; font-size: 12px; text-align: left; }
  th { padding: 10px 14px; font-size: 11px; font-weight: 600; color: var(--muted); background: var(--subtle); white-space: nowrap; border-bottom: 1px solid var(--line); }
  td { padding: 13px 14px; border-bottom: 1px solid var(--line); }
  tbody > tr:last-child > td { border-bottom: 0; }
  .user-row:hover, .user-row.expanded { background: var(--subtle); }
  .name-cell { min-width: 160px; }
  .user-toggle { display: inline-flex; align-items: center; gap: 8px; padding: 3px 0; border: 0; background: transparent; color: var(--text); text-align: left; font: inherit; font-weight: 600; cursor: pointer; }
  .chevron { color: var(--muted); }
  .badge { display: inline-flex; align-items: center; padding: 3px 9px; border-radius: 6px; font-size: 11px; font-weight: 500; white-space: nowrap; }
  .badge-admin { background: color-mix(in srgb, #a78bfa 16%, var(--surface)); color: var(--text); }
  .badge-write { background: color-mix(in srgb, #22c55e 14%, var(--surface)); color: var(--text); }
  .badge-read { background: var(--subtle); color: var(--muted); border: 1px solid var(--line); }
  .badge-type { background: var(--subtle); color: var(--muted); margin-left: 6px; font-size: 10px; }
  .actions-cell { white-space: nowrap; }
  .actions-cell .secondary-btn { margin-right: 6px; }
  .admin-table .role-select { min-width: 135px; min-height: 32px; padding: 5px 8px; font-size: 12px; }
  .detail-row > td { padding: 16px; background: var(--subtle); }
  .detail { border-left: 2px solid var(--color-accent, #f97316); padding: 0 16px; }
  .detail p { margin: 0 0 10px; }
  .hint { margin: 4px 0 0; color: var(--muted); font-size: 12px; line-height: 1.8; }
  @media (max-width: 1100px) {
    .settings-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .overview strong { font-size: 16px; }
    .overview > div { padding: 16px; }
  }
  @media (max-width: 700px) {
    .admin-page { padding: 20px 16px; }
    .page-header { align-items: flex-start; }
    .page-header > .badge { display: none; }
    h2 { font-size: 24px; }
    section { padding: 18px; }
    summary { padding: 18px; }
    .summary-hint { display: block; margin: 4px 0 0; }
    .auth-content { padding: 0 18px 18px; }
    .overview { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .overview > div:nth-child(3) { border-left: 0; }
    .overview > div:nth-child(n+3) { border-top: 1px solid var(--line); }
    .settings-grid, .create-form { grid-template-columns: 1fr; }
    .toggle { flex-wrap: wrap; }
    .create-form .create-btn { margin-top: 2px; }
  }
</style>
