<script>
  import { onMount } from "svelte";
  import {
    adminCreateUser,
    adminResetPassword,
    adminSetRole,
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

  onMount(refresh);

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
                    <option value="default">default (env)</option>
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
      count per minute per project). The Role column overrides the
      <span class="mono">TRACKIO_OIDC_*</span> environment defaults and takes
      effect immediately, including for active sessions; "default (env)"
      falls back to the environment configuration.
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
