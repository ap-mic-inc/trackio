<script>
  import CodeSnippet from "../components/CodeSnippet.svelte";

  let { project = null } = $props();

  let selectedGuide = $state("quickstart");
  let selectedStage = $state("pretrain");
  let selectedQuickstart = $state("log");

  function handleGuideTabKeydown(event, current) {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const next = event.key === "Home" ? "quickstart" : event.key === "End" ? "recipes" : current === "quickstart" ? "recipes" : "quickstart";
    selectedGuide = next;
    document.getElementById(`project-guide-tab-${next}`)?.focus();
  }

  const llmStages = [
    { id: "pretrain", label: "Pretraining" },
    { id: "sft", label: "SFT" },
    { id: "rl", label: "RLHF / RL" },
    { id: "evals", label: "Evals" },
  ];
  let stageCode = $derived.by(() => {
    const proj = project || "my-project";
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
  let quickstartCode = $derived.by(() => {
    const proj = project || "my-project";
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

</script>

<div class="project-guides">
  <div class="guide-switch" role="tablist" aria-label="Project guides">
    <button
      class="guide-switch-tab"
      class:active={selectedGuide === "quickstart"}
      id="project-guide-tab-quickstart"
      role="tab"
      aria-selected={selectedGuide === "quickstart"}
      aria-controls="project-guide-panel-quickstart"
      tabindex={selectedGuide === "quickstart" ? 0 : -1}
      onclick={() => { selectedGuide = "quickstart"; }}
      onkeydown={(event) => handleGuideTabKeydown(event, "quickstart")}
    >Python Quickstart</button>
    <button
      class="guide-switch-tab"
      class:active={selectedGuide === "recipes"}
      id="project-guide-tab-recipes"
      role="tab"
      aria-selected={selectedGuide === "recipes"}
      aria-controls="project-guide-panel-recipes"
      tabindex={selectedGuide === "recipes" ? 0 : -1}
      onclick={() => { selectedGuide = "recipes"; }}
      onkeydown={(event) => handleGuideTabKeydown(event, "recipes")}
    >LLM Training Recipes</button>
  </div>
  {#if selectedGuide === "quickstart"}
      <div class="guide-card" id="project-guide-panel-quickstart" role="tabpanel" aria-labelledby="project-guide-tab-quickstart" tabindex="0">
        <div class="guide-heading"><div><p class="guide-eyebrow">GET STARTED</p><h3 class="guide-title">Python Quickstart</h3></div><span class="guide-language">PYTHON</span></div>
        <p class="guide-desc">Copy-paste snippets for logging from your training script.</p>
        <div class="guide-tabs guide-subtabs">
          {#each quickstarts as q}
            <button
              class="guide-tab"
              class:active={selectedQuickstart === q.id}
              aria-pressed={selectedQuickstart === q.id}
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
      </div>
  {:else}
      <div class="guide-card" id="project-guide-panel-recipes" role="tabpanel" aria-labelledby="project-guide-tab-recipes" tabindex="0">
        <div class="guide-heading"><div><p class="guide-eyebrow">TRAINING PLAYBOOK</p><h3 class="guide-title">LLM Training Recipes</h3></div><span class="guide-language">4 STAGES</span></div>
        <p class="guide-desc">
          Stage-by-stage snippets for an LLM training pipeline, using the
          conventions this dashboard understands: metric prefixes like
          <code>train/</code>, <code>eval/</code>, and <code>perf/</code>
          become chart sections, and <code>group=</code> powers the sidebar's
          Group by. One project can hold every stage.
        </p>
        <div class="guide-tabs guide-subtabs">
          {#each llmStages as stage}
            <button
              class="guide-tab"
              class:active={selectedStage === stage.id}
              aria-pressed={selectedStage === stage.id}
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
      </div>
  {/if}
</div>

<style>
  .project-guides { margin: 0 0 28px; }
  .guide-switch { display: flex; flex-wrap: wrap; gap: 4px; border-bottom: 1px solid var(--border-color-primary); }
  .guide-switch-tab { flex-shrink: 0; padding: 10px 14px; border: 0; border-bottom: 2px solid transparent; margin-bottom: -1px; background: transparent; color: var(--body-text-color-subdued); font: inherit; font-size: 13px; font-weight: 500; cursor: pointer; white-space: nowrap; }
  .guide-switch-tab:hover { color: var(--body-text-color); }
  .guide-switch-tab.active { border-bottom-color: var(--primary-600); color: var(--body-text-color); font-weight: 600; }
  .guide-switch-tab:focus-visible { outline: 2px solid var(--color-accent); outline-offset: -2px; border-radius: var(--radius-sm); }
  .guide-card { min-width: 0; padding: 20px; border: 1px solid var(--border-color-primary); border-top: 0; border-radius: 0 0 var(--radius-xxl) var(--radius-xxl); background: var(--background-fill-primary); box-shadow: var(--shadow-drop); }
  .guide-heading { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
  .guide-eyebrow { margin: 0 0 5px; color: var(--color-accent); font-size: 10px; font-weight: 700; letter-spacing: .08em; }
  .guide-title { margin: 0; color: var(--body-text-color); font-size: 17px; font-weight: 600; letter-spacing: -.02em; }
  .guide-desc { min-height: 58px; margin: 8px 0 14px; color: var(--body-text-color-subdued); font-size: 12px; line-height: 1.55; }
  .guide-desc code, .quickstart-hint code { padding: 1px 4px; border-radius: 4px; background: var(--background-fill-secondary); font-size: 11px; }
  .guide-language { flex-shrink: 0; padding: 4px 7px; border: 1px solid var(--border-color-primary); border-radius: var(--radius-md); color: var(--body-text-color-subdued); font-size: 9px; font-weight: 600; letter-spacing: .04em; }
  .guide-tabs { display: flex; flex-wrap: wrap; gap: 5px; margin: 0 0 10px; }
  .guide-subtabs { margin-top: 16px; }
  .guide-tab { flex-shrink: 0; padding: 6px 9px; border: 1px solid transparent; border-radius: var(--radius-md); background: transparent; color: var(--body-text-color-subdued); font: inherit; font-size: 11px; cursor: pointer; }
  .guide-tab:hover { background: var(--background-fill-secondary); color: var(--body-text-color); }
  .guide-tab.active { border-color: var(--border-color-primary); background: var(--background-fill-secondary); color: var(--body-text-color); font-weight: 600; }
  .quickstart-hint { margin: 10px 0 0; color: var(--body-text-color-subdued); font-size: 11px; line-height: 1.55; }
  @media (max-width: 700px) { .guide-card { padding: 16px; } .guide-switch-tab { padding: 9px 10px; font-size: 12px; } .guide-tab { padding: 7px 10px; } }
</style>
