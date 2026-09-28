<script>
  import { copyTextToClipboard } from "../lib/clipboard.js";

  let { code = "" } = $props();

  let copied = $state(false);
  let timer = null;

  async function copy() {
    if (!(await copyTextToClipboard(code))) return;
    copied = true;
    clearTimeout(timer);
    timer = setTimeout(() => {
      copied = false;
    }, 1500);
  }
</script>

<div class="code-snippet">
  <pre><code>{code}</code></pre>
  <button
    class="snippet-copy"
    class:copied
    onclick={copy}
    title={copied ? "Copied" : "Copy to clipboard"}
    aria-label="Copy code to clipboard"
  >
    {#if copied}
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

<style>
  .code-snippet {
    position: relative;
    margin: 14px 0;
  }
  pre {
    margin: 0;
    padding: 14px 44px 14px 16px;
    overflow-x: auto;
    border: 1px solid var(--border-color-primary, #e5e7eb);
    border-radius: var(--radius-lg, 8px);
    background: var(--background-fill-secondary, #f9fafb);
    text-align: left;
    font-size: 12px;
    line-height: 1.7;
  }
  code {
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas,
      "Liberation Mono", "Courier New", monospace;
    color: var(--body-text-color, #1f2937);
  }
  .snippet-copy {
    position: absolute;
    top: 8px;
    right: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 5px;
    border: 1px solid var(--border-color-primary, #e5e7eb);
    border-radius: var(--radius-sm, 4px);
    background: var(--background-fill-primary, white);
    color: var(--body-text-color-subdued, #6b7280);
    cursor: pointer;
    opacity: 0.8;
    transition: opacity 0.15s, color 0.15s;
  }
  .snippet-copy:hover {
    opacity: 1;
    color: var(--body-text-color, #1f2937);
  }
  .snippet-copy.copied {
    opacity: 1;
    color: var(--color-accent, #f97316);
    border-color: var(--color-accent, #f97316);
  }
</style>
