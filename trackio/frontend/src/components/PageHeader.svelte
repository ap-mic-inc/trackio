<script>
  let { title, description = "", count = null } = $props();
</script>

<header class="page-heading">
  <div class="title-row">
    <h2>{title}</h2>
    {#if count !== null}<span class="count">{count}</span>{/if}
  </div>
  {#if description}<p>{description}</p>{/if}
</header>

<style>
  .page-heading { margin-bottom: 24px; }
  .title-row { display: flex; align-items: center; gap: 10px; }
  h2 { margin: 0; color: var(--body-text-color, #1f2937); font-size: 24px; font-weight: 600; letter-spacing: -.035em; line-height: 1.3; }
  p { margin: 6px 0 0; color: var(--body-text-color-subdued, #6b7280); font-size: 13px; line-height: 1.6; }
  .count { padding: 2px 8px; border: 1px solid var(--border-color-primary, #e5e7eb); border-radius: 6px; background: var(--background-fill-secondary, #f9fafb); color: var(--body-text-color-subdued, #6b7280); font-size: 12px; font-variant-numeric: tabular-nums; }
  @media (max-width: 700px) { h2 { font-size: 21px; } .page-heading { margin-bottom: 20px; } }
</style>
