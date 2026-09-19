<script>
  import PageHeader from "../components/PageHeader.svelte";
  import CodeSnippet from "../components/CodeSnippet.svelte";
  import { copyTextToClipboard } from "../lib/clipboard.js";
  import {
    getThemePreference,
    setThemePreference,
  } from "../lib/theme.js";

  let { spaceId = null, selectedProject = null, projects = [] } = $props();

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

  const llmStages = [
    { id: "pretrain", label: "Pretraining" },
    { id: "sft", label: "SFT" },
    { id: "rl", label: "RLHF / RL" },
    { id: "evals", label: "Evals" },
  ];
  let selectedStage = $state("pretrain");

  let stageCode = $derived.by(() => {
    const proj = cliProject || "my-project";
    const snippets = {
      pretrain: `import trackio

trackio.init(
    project="${proj}",
    name="pretrain-7b-v1",
    group="pretrain",
    config={"params": "7B", "lr": 3e-4, "global_batch": 1024, "seq_len": 4096},
)

for step in range(total_steps):
    metrics = train_step()
    trackio.log({
        "train/loss": metrics.loss,
        "train/grad_norm": metrics.grad_norm,
        "lr": scheduler.get_last_lr()[0],
        "perf/tokens_per_s": metrics.tokens_per_s,
        "perf/step_time_s": metrics.step_time,
    }, step=step)

trackio.finish()`,
      sft: `import trackio

trackio.init(
    project="${proj}",
    name="sft-v1",
    group="sft",
    config={"base_model": "pretrain-7b-v1", "lr": 2e-5, "epochs": 3},
)

for step, batch in enumerate(train_loader):
    loss = training_step(batch)
    trackio.log({"train/loss": loss, "lr": lr, "epoch": epoch}, step=step)
    if step % eval_every == 0:
        trackio.log({"eval/loss": evaluate()}, step=step)

trackio.finish()`,
      rl: `import trackio

trackio.init(
    project="${proj}",
    name="grpo-v1",
    group="rl",
    config={"algo": "grpo", "kl_coef": 0.05, "rollouts_per_step": 1024},
)

for it in range(iterations):
    stats = rl_step()
    trackio.log({
        "train/reward": stats.mean_reward,
        "train/kl": stats.kl,
        "train/policy_loss": stats.policy_loss,
        "train/entropy": stats.entropy,
        "rollout/response_len": stats.mean_response_len,
        "rollout/accept_rate": stats.accept_rate,
    }, step=it)

trackio.finish()`,
      evals: `import trackio
import pandas as pd

trackio.init(
    project="${proj}",
    name="eval-step-2000",
    group="eval",
    config={"checkpoint": "step-2000"},
)

trackio.log({"eval/mmlu": 0.62, "eval/gsm8k": 0.41, "eval/humaneval": 0.33})

df = pd.DataFrame({"prompt": prompts, "completion": completions, "score": scores})
trackio.log({"eval/samples": trackio.Table(dataframe=df)})

trackio.finish()`,
    };
    return snippets[selectedStage];
  });

  const quickstarts = [
    { id: "log", label: "Log metrics" },
    { id: "wandb", label: "Migrate from wandb" },
    { id: "resume", label: "Resume a run" },
  ];
  let selectedQuickstart = $state("log");

  let quickstartCode = $derived.by(() => {
    const proj = cliProject || "my-project";
    const snippets = {
      log: `import trackio

trackio.init(
    project="${proj}",
    name="my-run",
    config={"learning_rate": 1e-3, "epochs": 10},
)

for step in range(100):
    trackio.log({"train/loss": 1 / (step + 1)})

trackio.finish()`,
      wandb: `import trackio as wandb

wandb.init(project="${proj}", config={"learning_rate": 1e-3})
wandb.log({"train/loss": 0.42})
wandb.finish()`,
      resume: `import trackio

trackio.init(project="${proj}", name="my-run", resume="allow")
trackio.log({"train/loss": 0.05})
trackio.finish()`,
    };
    return snippets[selectedQuickstart];
  });

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
              class="selector-select"
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
        <h3 class="section-title">Python Quickstart</h3>
        <p class="section-desc">Copy-paste snippets for logging from your training script.</p>
        <div class="agent-tabs">
          {#each quickstarts as q}
            <button
              class="agent-tab"
              class:active={selectedQuickstart === q.id}
              onclick={() => { selectedQuickstart = q.id; }}
            >
              {q.label}
            </button>
          {/each}
        </div>
        <CodeSnippet code={quickstartCode} />
        {#if selectedQuickstart === "wandb"}
          <p class="quickstart-hint">
            Trackio is a drop-in replacement for <code>wandb</code>: change the import and keep the rest of your script.
          </p>
        {:else if selectedQuickstart === "resume"}
          <p class="quickstart-hint">
            <code>resume</code> accepts <code>"never"</code> (default), <code>"allow"</code>, or <code>"must"</code>.
          </p>
        {/if}
      </section>

      <section class="settings-section">
        <h3 class="section-title">LLM Training Recipes</h3>
        <p class="section-desc">
          Stage-by-stage snippets for an LLM training pipeline, using the
          conventions this dashboard understands: metric prefixes like
          <code>train/</code>, <code>eval/</code>, and <code>perf/</code>
          become chart sections, and <code>group=</code> powers the sidebar's
          Group by. One project can hold every stage.
        </p>
        <div class="agent-tabs">
          {#each llmStages as stage}
            <button
              class="agent-tab"
              class:active={selectedStage === stage.id}
              onclick={() => { selectedStage = stage.id; }}
            >
              {stage.label}
            </button>
          {/each}
        </div>
        <CodeSnippet code={stageCode} />
        {#if selectedStage === "pretrain"}
          <p class="quickstart-hint">
            Also worth tracking: <code>train/ppl</code>,
            <code>train/tokens_seen</code>, <code>perf/mfu</code>. Loss spikes
            are easiest to diagnose next to <code>train/grad_norm</code>, and
            GPU utilization is logged automatically when
            <code>nvidia-ml-py</code> is installed.
          </p>
        {:else if selectedStage === "sft"}
          <p class="quickstart-hint">
            <code>eval/loss</code> rising while <code>train/loss</code> keeps
            falling is the overfitting signal to watch. Log
            <code>epoch</code> too so you can switch the X-axis to it.
          </p>
        {:else if selectedStage === "rl"}
          <p class="quickstart-hint">
            Healthy runs show <code>train/reward</code> climbing while
            <code>train/kl</code> stays bounded; collapsing
            <code>train/entropy</code> or exploding
            <code>rollout/response_len</code> are early failure signals.
          </p>
        {:else if selectedStage === "evals"}
          <p class="quickstart-hint">
            One run per checkpoint (named after its step) keeps benchmarks
            comparable in the Runs table, and the samples table appears under
            Media &amp; Tables for side-by-side reading.
          </p>
        {/if}
      </section>

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
    font-size: var(--text-sm, 12px);
    color: var(--body-text-color-subdued, #6b7280);
    flex-shrink: 0;
  }
  .selector-select {
    padding: 6px 10px;
    border: 1px solid var(--border-color-primary, #e5e7eb);
    border-radius: var(--radius-md, 4px);
    background: var(--background-fill-primary, white);
    color: var(--body-text-color, #1f2937);
    font-size: var(--text-sm, 12px);
    min-width: 160px;
    cursor: pointer;
  }
  .selector-select:focus {
    outline: none;
    border-color: var(--color-accent, #f97316);
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
  .quickstart-hint {
    margin: 10px 0 0;
    font-size: var(--text-sm, 12px);
    color: var(--body-text-color-subdued, #6b7280);
    line-height: 1.6;
  }
  .quickstart-hint code {
    font-size: 11px;
    padding: 1px 5px;
    border-radius: 4px;
    background: var(--background-fill-secondary, #f9fafb);
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
