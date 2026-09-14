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
  let createMessage = $state(null);

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
  <h2>Users & Access</h2>
  <p class="subtitle">
    {#if oidcEnabled}
      OIDC login is enabled.
      {authRequired
        ? "The whole dashboard requires sign-in."
        : "Dashboards are public; writes require sign-in or a write token."}
    {:else}
      OIDC login is not configured. Only write-token access is available.
    {/if}
  </p>

  {#if error}
    <p class="error">{error}</p>
  {/if}

  {#if loading}
    <p class="muted">Loading…</p>
  {:else if !isAdmin}
    <p class="error">Admin access is required to view this page.</p>
  {:else}
    {#if authSettings}
      <section>
        <h3>Authentication settings</h3>
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
            <label>Allowed users (comma-separated)
              <input bind:value={authSettings.allowed_users} placeholder="empty = anyone at the IdP" />
            </label>
            <label>Allowed groups
              <input bind:value={authSettings.allowed_groups} />
            </label>
            <label>Write users
              <input bind:value={authSettings.write_users} placeholder="empty = all signed-in users, * = everyone" />
            </label>
            <label>Write groups
              <input bind:value={authSettings.write_groups} />
            </label>
            <label>Admin users
              <input bind:value={authSettings.admin_users} />
            </label>
            <label>Admin groups
              <input bind:value={authSettings.admin_groups} />
            </label>
          </div>
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
            {#if settingsMessage}<span class="muted">{settingsMessage}</span>{/if}
            {#if testMessage}<span class="muted">{testMessage}</span>{/if}
          </div>
        </form>
      </section>
    {/if}

    <section>
      <h3>Users ({users.length})</h3>
      {#if users.length === 0}
        <p class="muted">
          No users yet. The first admin account is registered on the
          <span class="mono">/setup</span> page.
        </p>
      {:else}
        <table class="admin-table">
          <thead>
            <tr>
              <th>User</th>
              <th>Email</th>
              <th>Access</th>
              <th>Role</th>
              <th>Last login</th>
              <th>Logins</th>
              <th>Sessions</th>
              <th>Projects</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {#each users as user (user.sub)}
              <tr class="user-row" onclick={() => toggleExpand(user.sub)}>
                <td class="name-cell">
                  {displayName(user)}
                  {#if user.auth_type === "local"}
                    <span class="badge badge-type">local</span>
                  {/if}
                </td>
                <td class="muted">{user.email ?? "—"}</td>
                <td>
                  {#if user.is_admin}
                    <span class="badge badge-admin">admin</span>
                  {:else if user.can_write}
                    <span class="badge badge-write">write</span>
                  {:else}
                    <span class="badge badge-read">read-only</span>
                  {/if}
                </td>
                <td>
                  <select
                    class="role-select"
                    value={currentRole(user)}
                    onclick={(e) => e.stopPropagation()}
                    onchange={(e) => changeRole(user.sub, e.target.value)}
                  >
                    <option value="default">default (write)</option>
                    <option value="admin">admin</option>
                    <option value="write">write</option>
                    <option value="read">read-only</option>
                  </select>
                </td>
                <td class="muted">{user.last_login ?? "—"}</td>
                <td class="muted">{user.login_count}</td>
                <td class="muted">{user.active_sessions}</td>
                <td class="muted">{user.projects.length}</td>
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
                  <td colspan="9">
                    <div class="detail">
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
      {/if}
    </section>

    <section>
      <h3>Create local account</h3>
      <p class="muted">
        Password-based account managed by this server (independent of the
        OIDC provider). The user signs in on the
        <span class="mono">/login</span> page.
      </p>
      <form class="create-form" onsubmit={createUser}>
        <input
          placeholder="username"
          bind:value={newUsername}
          autocomplete="off"
        />
        <input
          placeholder="password (min 8 chars)"
          type="password"
          bind:value={newPassword}
          autocomplete="new-password"
        />
        <select class="role-select" bind:value={newRole}>
          <option value="admin">admin</option>
          <option value="write">write</option>
          <option value="read">read-only</option>
        </select>
        <button class="create-btn" type="submit" disabled={creating}>
          {creating ? "Creating…" : "Create user"}
        </button>
      </form>
      {#if createMessage}
        <p class="muted">{createMessage}</p>
      {/if}
    </section>

    <section>
      <h3>Write-token clients</h3>
      <p class="muted">
        Projects written by scripts authenticating with the server write token
        (no user identity).
      </p>
      {#if writeTokenProjects.length === 0}
        <p class="muted">No write-token activity recorded.</p>
      {:else}
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
      {/if}
    </section>

    <p class="hint">
      Activity timestamps are UTC. High-frequency logging is aggregated (one
      count per minute per project). The Role column takes effect
      immediately, including for active sessions. "default (write)" means
      read-write access, or whatever the configured allowed/write lists
      resolve to for OIDC users when those lists are set.
    </p>
  {/if}
</div>

<style>
  .admin-page {
    padding: 24px 32px;
    max-width: 1100px;
    overflow-y: auto;
  }
  h2 {
    margin: 0 0 4px;
    font-size: 20px;
    color: var(--body-text-color, #1f2937);
  }
  h3 {
    margin: 28px 0 8px;
    font-size: 15px;
    color: var(--body-text-color, #1f2937);
  }
  .subtitle {
    margin: 0 0 16px;
    font-size: 13px;
    color: var(--body-text-color-subdued, #6b7280);
  }
  .muted {
    color: var(--body-text-color-subdued, #6b7280);
    font-size: 13px;
  }
  .mono {
    font-family: var(--font-mono, monospace);
    font-size: 12px;
  }
  .error {
    color: #dc2626;
    font-size: 13px;
  }
  .admin-table,
  .project-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
  }
  .admin-table th,
  .project-table th {
    text-align: left;
    padding: 8px 10px;
    font-weight: 500;
    color: var(--body-text-color-subdued, #6b7280);
    border-bottom: 1px solid var(--border-color-primary, #e5e7eb);
    white-space: nowrap;
  }
  .admin-table td,
  .project-table td {
    padding: 8px 10px;
    border-bottom: 1px solid var(--border-color-primary, #f3f4f6);
    color: var(--body-text-color, #1f2937);
  }
  .user-row {
    cursor: pointer;
  }
  .user-row:hover td {
    background: var(--background-fill-secondary, #f9fafb);
  }
  .name-cell {
    font-weight: 500;
  }
  .badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 600;
  }
  .badge-admin {
    background: #ede9fe;
    color: #6d28d9;
  }
  .badge-write {
    background: #dcfce7;
    color: #15803d;
  }
  .badge-read {
    background: var(--background-fill-secondary, #f3f4f6);
    color: var(--body-text-color-subdued, #6b7280);
  }
  .badge-type {
    background: #e0f2fe;
    color: #0369a1;
    margin-left: 6px;
  }
  .actions-cell {
    white-space: nowrap;
  }
  .secondary-btn {
    padding: 4px 10px;
    margin-right: 6px;
    font-size: 12px;
    border: 1px solid var(--border-color-primary, #e5e7eb);
    border-radius: 6px;
    background: var(--background-fill-primary, white);
    color: var(--body-text-color, #374151);
    cursor: pointer;
  }
  .secondary-btn:hover {
    background: var(--background-fill-secondary, #f9fafb);
  }
  .settings-form {
    display: flex;
    flex-direction: column;
    gap: 12px;
    margin-top: 8px;
  }
  .settings-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: 10px 16px;
  }
  .settings-grid label,
  .toggle {
    font-size: 12px;
    color: var(--body-text-color-subdued, #6b7280);
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .toggle {
    flex-direction: row;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    color: var(--body-text-color, #1f2937);
  }
  .settings-grid input {
    padding: 6px 10px;
    font-size: 13px;
    border: 1px solid var(--border-color-primary, #e5e7eb);
    border-radius: 6px;
    background: var(--background-fill-primary, white);
    color: var(--body-text-color, #1f2937);
  }
  .settings-actions {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }
  .create-form {
    display: flex;
    gap: 8px;
    align-items: center;
    margin-top: 8px;
    flex-wrap: wrap;
  }
  .create-form input {
    padding: 6px 10px;
    font-size: 13px;
    border: 1px solid var(--border-color-primary, #e5e7eb);
    border-radius: 6px;
    background: var(--background-fill-primary, white);
    color: var(--body-text-color, #1f2937);
  }
  .create-btn {
    padding: 6px 14px;
    font-size: 13px;
    font-weight: 600;
    color: white;
    background: rgb(20, 28, 46);
    border: none;
    border-radius: 6px;
    cursor: pointer;
  }
  .create-btn:hover:not(:disabled) {
    background: rgb(40, 48, 66);
  }
  .create-btn:disabled {
    opacity: 0.6;
  }
  .role-select {
    padding: 3px 6px;
    font-size: 12px;
    border: 1px solid var(--border-color-primary, #e5e7eb);
    border-radius: 6px;
    background: var(--background-fill-primary, white);
    color: var(--body-text-color, #1f2937);
    cursor: pointer;
  }
  .revoke-btn {
    padding: 4px 10px;
    font-size: 12px;
    border: 1px solid var(--border-color-primary, #e5e7eb);
    border-radius: 6px;
    background: var(--background-fill-primary, white);
    color: #dc2626;
    cursor: pointer;
  }
  .revoke-btn:hover:not(:disabled) {
    background: #fef2f2;
  }
  .revoke-btn:disabled {
    opacity: 0.6;
    cursor: default;
  }
  .detail-row td {
    background: var(--background-fill-secondary, #f9fafb);
  }
  .detail {
    padding: 4px 8px 8px;
  }
  .project-table.standalone {
    margin-top: 8px;
  }
  .hint {
    margin-top: 24px;
    font-size: 12px;
    color: var(--body-text-color-subdued, #9ca3af);
  }
</style>
