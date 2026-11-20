# OFB Docs Tracker

Tracks changes to Open Finance Brasil Confluence pages and publishes the diffs to GitHub Pages.

- **Add/remove a page:** edit `pages.txt` (one URL or page ID per line) and push. The workflow backfills the full version history of new pages automatically.
- **Run locally:** `python3 fetch.py && python3 build_site.py && open site/index.html`
- **Run on GitHub now:** Actions tab → `track` → Run workflow (or `gh workflow run track`).
