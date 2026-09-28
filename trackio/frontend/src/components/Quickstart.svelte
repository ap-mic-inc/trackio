<script>
  import CodeSnippet from "./CodeSnippet.svelte";

  let {
    guide,
    collapsible = false,
    open = $bindable(false),
    selectedId = $bindable(null),
  } = $props();
  let selected = $derived(
    guide.items.find((item) => item.id === selectedId) ?? guide.items[0],
  );
</script>

{#snippet guideContent()}
  <div class="guide-card" class:attached={collapsible}>
    <div class="guide-heading">
      <div>
        <p class="guide-eyebrow">{guide.eyebrow}</p>
        <h3 class="guide-title">{guide.title}</h3>
      </div>
      <span class="guide-language">{selected.badge ?? guide.badge}</span>
    </div>
    <p class="guide-desc">{@html guide.description}</p>
    {#if guide.items.length > 1}
      <div class="guide-tabs">
        {#each guide.items as item (item.id)}
          <button
            class="guide-tab"
            class:active={selected.id === item.id}
            aria-pressed={selected.id === item.id}
            onclick={() => { selectedId = item.id; }}
          >
            {item.label}
          </button>
        {/each}
      </div>
    {/if}
    <CodeSnippet code={selected.code} />
    {#if selected.hint}
      <div class="quickstart-hint">{@html selected.hint}</div>
    {/if}
  </div>
{/snippet}

{#if collapsible}
  <details class="quickstart-collapsible" bind:open>
    <summary>Quickstart <span>{guide.summary}</span></summary>
    {@render guideContent()}
  </details>
{:else}
  <div class="quickstart">
    {@render guideContent()}
  </div>
{/if}

<style>
  .quickstart { margin: 0 0 28px; }
  .quickstart-collapsible { margin: 0 0 22px; }
  .quickstart-collapsible > summary { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 11px 14px; border: 1px solid var(--border-color-primary); border-radius: var(--radius-lg); background: var(--background-fill-primary); color: var(--body-text-color); font-size: 13px; font-weight: 600; cursor: pointer; list-style: none; }
  .quickstart-collapsible > summary::-webkit-details-marker { display: none; }
  .quickstart-collapsible > summary::after { content: "+"; color: var(--body-text-color-subdued); font-size: 16px; font-weight: 400; }
  .quickstart-collapsible[open] > summary { border-radius: var(--radius-lg) var(--radius-lg) 0 0; }
  .quickstart-collapsible[open] > summary::after { content: "−"; }
  .quickstart-collapsible > summary span { margin-left: auto; color: var(--body-text-color-subdued); font-size: 11px; font-weight: 400; }
  .guide-card { min-width: 0; padding: 20px; border: 1px solid var(--border-color-primary); border-radius: var(--radius-xxl); background: var(--background-fill-primary); box-shadow: var(--shadow-drop); }
  .guide-card.attached { border-top: 0; border-radius: 0 0 var(--radius-xxl) var(--radius-xxl); }
  .guide-heading { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
  .guide-eyebrow { margin: 0 0 5px; color: var(--color-accent); font-size: 10px; font-weight: 700; letter-spacing: .08em; }
  .guide-title { margin: 0; color: var(--body-text-color); font-size: 17px; font-weight: 600; letter-spacing: -.02em; }
  .guide-desc { margin: 8px 0 14px; color: var(--body-text-color-subdued); font-size: 12px; line-height: 1.55; }
  .guide-desc :global(code), .quickstart-hint :global(code) { padding: 1px 4px; border-radius: 4px; background: var(--background-fill-secondary); font-size: 11px; }
  .guide-language { flex-shrink: 0; padding: 4px 7px; border: 1px solid var(--border-color-primary); border-radius: var(--radius-md); color: var(--body-text-color-subdued); font-size: 9px; font-weight: 600; letter-spacing: .04em; }
  .guide-tabs { display: flex; flex-wrap: wrap; gap: 5px; margin: 16px 0 10px; }
  .guide-tab { flex-shrink: 0; padding: 6px 9px; border: 1px solid transparent; border-radius: var(--radius-md); background: transparent; color: var(--body-text-color-subdued); font: inherit; font-size: 11px; cursor: pointer; }
  .guide-tab:hover { background: var(--background-fill-secondary); color: var(--body-text-color); }
  .guide-tab.active { border-color: var(--border-color-primary); background: var(--background-fill-secondary); color: var(--body-text-color); font-weight: 600; }
  .quickstart-hint :global(ul) { margin: 0; padding-left: 16px; }
  .quickstart-hint :global(li + li) { margin-top: 4px; }
  .quickstart-hint { margin: 10px 0 0; color: var(--body-text-color-subdued); font-size: 11px; line-height: 1.55; }
  @media (max-width: 700px) { .guide-card { padding: 16px; } .guide-tab { padding: 7px 10px; } }
</style>
