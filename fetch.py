"""Download every Confluence version of each page in pages.txt that isn't saved yet.

For page 1621622796, version 25 it writes:
  snapshots/1621622796/v0025.html   the page body exactly as Confluence stores it
  snapshots/1621622796/v0025.json   metadata: title, edit time, author, edit message

Already-saved versions are never re-downloaded, so this is cheap to run hourly.
Usage: python3 fetch.py
"""
import json
import time
import urllib.error
import urllib.request

from common import SITE, SNAPSHOTS, read_page_ids

API = SITE + "/wiki/rest/api/content"


def get_json(url, tries=4):
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "ofb-docs-tracker"})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError) as e:
            # 404 is permanent (page deleted/private); everything else gets retried
            if isinstance(e, urllib.error.HTTPError) and e.code == 404:
                raise
            if attempt == tries - 1:
                raise
            wait = 5 * 2 ** attempt
            print(f"  retrying in {wait}s after error: {e}")
            time.sleep(wait)


def fix_mojibake(s):
    """Confluence returns some edit messages double-encoded ('padrÃ£o' instead of 'padrão')."""
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def list_version_numbers(page_id):
    numbers, url = [], f"{API}/{page_id}/version?limit=200"
    while url:
        data = get_json(url)
        numbers += [v["number"] for v in data["results"]]
        nxt = data.get("_links", {}).get("next")
        url = SITE + "/wiki" + nxt if nxt else None
    return sorted(numbers)


def fetch_page(page_id):
    folder = SNAPSHOTS / page_id
    folder.mkdir(parents=True, exist_ok=True)
    have = {int(p.stem[1:]) for p in folder.glob("v*.json")}
    missing = [n for n in list_version_numbers(page_id) if n not in have]
    for n in missing:
        d = get_json(f"{API}/{page_id}?status=historical&version={n}&expand=version,body.storage,space")
        v = d["version"]
        meta = {
            "page_id": page_id,
            "version": v["number"],
            "title": d["title"],
            "space": d.get("space", {}).get("key", ""),
            "when": v["when"],
            "author": v.get("by", {}).get("displayName") or v.get("by", {}).get("publicName") or "",
            "message": fix_mojibake(v.get("message", "")),
            "minor_edit": v.get("minorEdit", False),
        }
        stem = f"v{n:04d}"
        (folder / f"{stem}.html").write_text(d["body"]["storage"]["value"], encoding="utf-8")
        (folder / f"{stem}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"  saved {page_id} v{n}  ({meta['when']})  {meta['title']}")
    return len(missing)


def main():
    total, failed = 0, []
    for page_id in read_page_ids():
        print(f"page {page_id}")
        try:
            total += fetch_page(page_id)
        except Exception as e:  # one broken page must not stop the others
            print(f"  ERROR: {e}")
            failed.append(page_id)
    print(f"done: {total} new version(s) saved")
    if failed:
        raise SystemExit(f"failed pages: {', '.join(failed)}")


if __name__ == "__main__":
    main()
