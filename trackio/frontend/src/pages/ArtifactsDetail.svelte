<script>
  import ArtifactVersionDetail from "../components/ArtifactVersionDetail.svelte";
  import Quickstart from "../components/Quickstart.svelte";
  import { artifactsGuide } from "../lib/quickstarts.js";

  let {
    project = null,
    selection = null,
    empty = false,
    onOpenVersion = null,
  } = $props();
</script>

<div class="detail-pane workspace-page">
  {#if project}
    <Quickstart guide={artifactsGuide(project)} collapsible={true} />
  {/if}
  {#if selection}
    {#key `${selection.name}@v${selection.version}`}
      <ArtifactVersionDetail
        variant="panel"
        {project}
        name={selection.name}
        version={selection.version}
        {onOpenVersion}
      />
    {/key}
  {:else if empty}
    <div class="empty-state">
      <h2>No artifacts in this project</h2>
      <p>
        Artifacts are versioned, content-addressed files (models, datasets, …)
        logged from a run. After <code>trackio.init()</code>, log one with
        <code>trackio.log_artifact()</code>:
      </p>
      <pre><code
          >{'import trackio\n\ntrackio.init(project="my-project")\ntrackio.log_artifact("model.pt", name="my-model", type="model")'}</code
        ></pre>
      <p>
        You can also build a multi-file artifact with
        <code>add_file()</code>/<code>add_dir()</code>. Logged artifacts list
        here, grouped by type, with their versions and files.
      </p>
    </div>
  {:else}
    <div class="detail-empty">
      Select an artifact version to view its details.
    </div>
  {/if}
</div>

<style>
  .detail-pane {
    flex: 1;
    min-width: 0;
    overflow-y: auto;
    padding: 20px 28px;
  }
  .detail-empty {
    color: var(--body-text-color-subdued, #6b7280);
    font-size: var(--text-sm, 13px);
    padding: 12px 0;
  }
</style>
