<script>
  let { label = "", open = $bindable(true), hidden = false, children } = $props();

  function toggle() {
    open = !open;
  }
</script>

{#if hidden}
  <div class="accordion-hidden">
    {#if children}{@render children()}{/if}
  </div>
{:else}
  <div class="accordion">
    <button class="accordion-header" onclick={toggle}>
      <span class="arrow" class:rotated={open}>▾</span>
      <span class="accordion-label">{label}</span>
    </button>
    {#if open}
      <div class="accordion-body">
        {#if children}{@render children()}{/if}
      </div>
    {/if}
  </div>
{/if}

<style>
  .accordion {
    margin-bottom: 28px;
  }
  .accordion-hidden {
    margin-bottom: 16px;
  }
  .accordion-header {
    display: flex;
    align-items: center;
    gap: 7px;
    width: 100%;
    padding: 0 0 10px;
    border: none;
    background: none;
    color: var(--body-text-color, #1f2937);
    font-size: var(--text-md, 14px);
    font-weight: 600;
    letter-spacing: -0.01em;
    cursor: pointer;
    text-align: left;
  }
  .accordion-header:hover .arrow {
    color: var(--body-text-color, #1f2937);
  }
  .arrow {
    font-size: 12px;
    transition: transform 0.15s, color 0.15s;
    color: var(--body-text-color-subdued, #9ca3af);
    display: inline-block;
  }
  .arrow:not(.rotated) {
    transform: rotate(-90deg);
  }
  .accordion-body {
    padding: 0;
  }
</style>
