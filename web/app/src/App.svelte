<script>
  import './app.css';
  import Nav from './lib/components/Nav.svelte';
  import Footer from './lib/components/Footer.svelte';
  import { router } from './lib/router.svelte.js';
</script>

<Nav />

<main class="main">
  <div class="page-enter">
    {#if router.loading}
      <div class="loading">
        <div class="spinner"></div>
      </div>
    {:else if router.component}
      {#key router.navCount}
        <router.component params={router.params} />
      {/key}
    {:else}
      <div class="error-page">
        <h1>404</h1>
        <p>Page not found. Henry hasn't played this track yet.</p>
        <a href="#/" onclick={router.navigate} class="back-link">→ Back to the show</a>
      </div>
    {/if}
  </div>
</main>

<Footer />

<style>
  .main {
    max-width: 1280px;
    margin: 0 auto;
    padding: 2rem 1.5rem;
  }
  .loading {
    display: flex;
    justify-content: center;
    padding: 4rem 0;
  }
  .spinner {
    width: 32px;
    height: 32px;
    border: 3px solid var(--color-henry-600);
    border-top-color: var(--color-accent);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
  @keyframes spin {
    to { transform: rotate(360deg); }
  }
  .error-page {
    text-align: center;
    padding: 4rem 1rem;
  }
  .error-page h1 {
    font-size: 4rem;
    margin: 0;
    color: var(--color-henry-400);
  }
  .error-page p {
    color: var(--color-henry-300);
    margin: 1rem 0;
  }
  .back-link {
    color: var(--color-accent);
    text-decoration: none;
    font-weight: 600;
  }
  .back-link:hover {
    text-decoration: underline;
  }
</style>
