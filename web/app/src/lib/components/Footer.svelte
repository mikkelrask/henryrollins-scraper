<footer class="footer">
  <div class="footer-inner">
    <div class="footer-links">
      <a href="https://www.henryrollins.com" target="_blank" rel="noopener noreferrer" class="footer-link">
        henryrollins.com
      </a>
      <a href="https://kcrw.com/shows/henry-rollins/latest" target="_blank" rel="noopener noreferrer" class="footer-link">
        KCRW - Henry Rollins
      </a>
      <a href="#/recommends" class="footer-link">Bandcamp Links</a>
      <a href="https://github.com/mikkelrask/henryrollins-scraper" target="_blank" rel="noopener noreferrer" class="footer-link">
        GitHub
      </a>
    </div>
    <div class="footer-meta">
      Play data from <a href="https://www.henryrollins.com/radio" target="_blank" rel="noopener noreferrer" class="footer-inline-link">henryrollins.com/radio</a>, enriched with data from <a href="https://musicbrainz.org" target="_blank" class="footer-inline-link">Musicbrainz</a> and <a href="https://last.fm" target="_blank" class="footer-inline-link">Last.fm</a>.
    </div>
  </div>
</footer>

<style>
  .footer {
    margin-top: 4rem;
    border-top: 1px solid var(--color-henry-700);
    background: var(--color-henry-900);
  }
  .footer-inner {
    max-width: 1280px;
    margin: 0 auto;
    padding: 2rem 1.5rem;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.75rem;
  }
  .footer-links {
    display: flex;
    gap: 1.5rem;
    flex-wrap: wrap;
    justify-content: center;
  }
  .footer-link {
    color: var(--color-henry-300);
    text-decoration: none;
    font-size: 0.85rem;
    font-weight: 500;
    transition: color 0.2s;
  }
  .footer-link:hover {
    color: var(--color-accent);
  }
  .footer-meta {
    color: var(--color-henry-400);
    font-size: 0.75rem;
  }
  .footer-inline-link {
    color: var(--color-henry-300);
    text-decoration: none;
    transition: color 0.2s;
  }
  .footer-inline-link:hover {
    color: var(--color-accent);
  }
</style>
