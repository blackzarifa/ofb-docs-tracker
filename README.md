# OFB Docs Tracker

Tracks changes to [Open Finance Brasil Confluence](https://openfinancebrasil.atlassian.net/wiki/spaces/OF) pages and publishes a readable change log.

**Site:** https://blackzarifa.github.io/ofb-docs-tracker/

Bacen edits these pages without notice, and Confluence doesn't show what changed between versions. This repo saves every version of each tracked page and publishes a site listing every change, grouped by day (Brasília time, newest first), with red/green diffs and word-level highlighting.

---

## How it works

```
 every hour (GitHub Actions, .github/workflows/track.yml)
 │
 ├─ 1. fetch.py        asks Confluence which versions of each page in pages.txt exist,
 │                     downloads only the ones not yet in snapshots/
 │
 ├─ 2. git commit      saves new files in snapshots/ to this repo
 │                     (commits by "github-actions[bot]")
 │
 ├─ 3. build_site.py   turns snapshots/ into site/index.html (all the diffs)
 │
 └─ 4. deploy          publishes site/ to GitHub Pages
```

Everything runs on GitHub's servers. Your computer doesn't need to be on.

### Why it never misses an edit

Confluence numbers every edit (v1, v2, v3…) and keeps every old version, publicly readable through its REST API. `fetch.py` doesn't just take a snapshot of how the page looks right now. It compares the version numbers Confluence reports with the ones already saved and downloads each missing one. So:

- If a page is edited 3 times within an hour, all 3 versions are saved.
- Dates on the site are the real edit times from Confluence, not when this job ran.
- When you add a page, its full history back to v1 is downloaded on the next run.

### Where the data comes from

Two public Confluence REST API endpoints. No login or API token is needed because the pages are public.

| Request | Returns |
|---|---|
| `GET /wiki/rest/api/content/{id}/version` | list of all version numbers of a page |
| `GET /wiki/rest/api/content/{id}?status=historical&version={n}&expand=version,body.storage` | one version: body, title, edit time, author, edit message |

`body.storage` is Confluence's internal XHTML format for the page, not the rendered HTML you see in a browser.

---

## Adding or removing a page

Edit [`pages.txt`](pages.txt). Put one page per line, either the full URL or just the numeric ID:

```
https://openfinancebrasil.atlassian.net/wiki/spaces/OF/pages/1621622796
1622081540
# lines starting with # are ignored
```

Then commit and push (or edit the file directly on github.com and click **Commit changes**). The push starts a run right away, and a new page appears on the site with its full history within about a minute.

Removing a line stops tracking the page and hides it from the site. Its saved versions stay in `snapshots/`.

---

## Reading the site

Each entry is one Confluence edit:

```
14:00 ● Pagamentos Automáticos - Regras… v32 → v33  −2 +3  André Shimizu
      "T-25; D-33 tamanho de companyProfileInfo"          ← author's edit message, if any
```

- **−N +M**: number of lines removed and added.
- Click an entry to open or close it. The 3 most recent entries that have text changes start open.
- **Checkboxes** at the top filter the list by page.
- **"ver vN no Confluence ↗"** opens that exact version on Confluence.

Inside a diff:

| You see | Meaning |
|---|---|
| red line, `−` | line as it was before |
| green line, `+` | line as it is now |
| darker red / green highlight inside a line | the exact words that changed |
| grey line | unchanged context around a change |
| `⋯` | unchanged lines skipped |
| `■ paymentId` | start of a table row (the value in its first column) |
| `paymentId › Padrão: ^[a-z…` | one table cell: row `paymentId`, column `Padrão` |
| `Colunas: Campo │ Definição │ …` | the table's header row |
| `• text` / `# text` | list item / heading |
| <kbd>ZWSP</kbd> box | an invisible character (zero-width space, etc.) was added or removed. These matter when copy-pasting endpoints or regexes. |

Tags instead of a diff:

- **página criada**: the page's first version (nothing to compare against).
- **só formatação**: the version changed only styling or internal attributes. The visible text is identical.

---

## Running locally

Requires Python 3.9+, standard library only (nothing to install).

```sh
python3 fetch.py         # download any new versions into snapshots/
python3 build_site.py    # write site/index.html
open site/index.html     # macOS: open it in your browser
```

`site/` is in `.gitignore` because it's rebuilt on every run and never committed.

Since GitHub commits new snapshots to this repo every hour, run `git pull` before changing anything locally.

---

## Running on GitHub

- **Automatically:** every hour at about minute 17 (UTC; GitHub can start it a few minutes late), on every push to `main`, and when you start it manually.
- **Manually:** **Actions** tab → **track** → **Run workflow**, or `gh workflow run track`.
- **See past runs:** **Actions** tab, or `gh run list`.

---

## Maintenance

**Normally: none.**

- **Dependabot** ([`.github/dependabot.yml`](.github/dependabot.yml)) checks weekly for new major versions of the GitHub-provided steps used in `track.yml` (`actions/checkout`, `actions/deploy-pages`, …). When one exists, it opens a pull request. Merge it, and the next run uses the new version.
- **Keepalive:** GitHub disables hourly workflows in repos with no commits for 60 days. If no page has changed in 45 days, the workflow makes an empty commit to prevent that.

**If a run fails**, GitHub emails the repo owner and the run shows a red ✗ in the Actions tab. Click it to see which step failed:

| Failing step | Likely cause | Fix |
|---|---|---|
| Fetch new Confluence versions, `HTTP Error 404` on one page | page deleted, moved, or made private | remove or update its line in `pages.txt` |
| Fetch, `401`/`403`/`404` on every page | Atlassian started requiring login | create an Atlassian API token at https://id.atlassian.com/manage-profile/security/api-tokens, store it as a repo secret, and add Basic auth to `get_json()` in `fetch.py` |
| Fetch, timeouts / `5xx` | Atlassian outage (already retried 4 times) | nothing; the next hourly run catches up and saves every missed version |
| Commit new snapshots, push rejected | you pushed at the same moment as the bot | nothing; the next run retries |
| deploy / configure-pages | Pages disabled in repo settings | **Settings → Pages → Source: GitHub Actions** |

---

## Files

| File | What it does |
|---|---|
| [`pages.txt`](pages.txt) | List of pages to track. |
| [`fetch.py`](fetch.py) | Downloads missing versions from the Confluence API into `snapshots/`. Retries network errors. One failing page doesn't stop the others. Repairs broken accents in edit messages (Atlassian returns `padrÃ£o` instead of `padrão`). |
| [`build_site.py`](build_site.py) | Converts each saved version into readable lines, diffs consecutive versions with Python's built-in `difflib`, and writes `site/index.html`. |
| [`common.py`](common.py) | Shared by both scripts. Reads `pages.txt` and extracts page IDs. Also holds the folder paths and the Atlassian base URL. |
| [`snapshots/<page-id>/vNNNN.html`](snapshots) | One version's page body, exactly as Confluence stores it. |
| [`snapshots/<page-id>/vNNNN.json`](snapshots) | That version's title, edit time (UTC), author, edit message. |
| [`.github/workflows/track.yml`](.github/workflows/track.yml) | The hourly GitHub Actions job (fetch → commit → build → deploy). |
| [`.github/dependabot.yml`](.github/dependabot.yml) | Weekly Dependabot check for newer versions of the actions used in `track.yml`. |
| `.gitignore` | Keeps `site/`, Python cache files and `.DS_Store` out of git. |
