<script module>
  export const DEFAULT_LOGO_URLS = {
    light: "/static/trackio/trackio_logo_type_light_transparent.png",
    dark: "/static/trackio/trackio_logo_type_dark_transparent.png",
  };
</script>

<script>
  import { onMount } from "svelte";
  import { getTrackioVersion } from "../lib/api.js";
  import { navigateTo } from "../lib/router.js";

  let { logoUrls = DEFAULT_LOGO_URLS, darkMode = false } = $props();
  let version = $state(null);

  onMount(async () => {
    try {
      version = await getTrackioVersion();
    } catch {
      version = null;
    }
  });
</script>

<div class="logo-section">
  <button
    class="logo-home"
    type="button"
    aria-label="Go to home"
    title="Go to home"
    onclick={() => navigateTo("overview")}
  >
    <img
      src={darkMode ? logoUrls.dark : logoUrls.light}
      alt=""
      class="logo"
    />
  </button>
  {#if version}
    <span class="version">APMIC v {version}</span>
  {/if}
</div>

<style>
  .logo-section {
    position: relative;
    width: 80%;
    max-width: 200px;
    margin-bottom: 20px;
  }
  .logo {
    display: block;
    width: 100%;
  }
  .logo-home {
    display: block;
    width: 100%;
    padding: 0;
    border: 0;
    background: transparent;
    cursor: pointer;
  }
  .logo-home:focus-visible {
    outline: 2px solid var(--color-accent, #f97316);
    outline-offset: 3px;
    border-radius: 3px;
  }
  .version {
    position: absolute;
    right: 5%;
    bottom: -2px;
    color: var(--body-text-color-subdued, #6b7280);
    font-size: 9px;
    font-weight: 500;
    line-height: 1;
    letter-spacing: 0.02em;
    opacity: 0.72;
  }
</style>
