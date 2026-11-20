"""Shared helpers for fetch.py and build_site.py (standard library only)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAGES_FILE = ROOT / "pages.txt"
SNAPSHOTS = ROOT / "snapshots"
SITE = "https://openfinancebrasil.atlassian.net"


def read_page_ids():
    """Return page IDs from pages.txt, in file order, without duplicates.

    Accepts full URLs (…/pages/1621622796/Title) or bare numeric IDs.
    """
    ids = []
    for raw in PAGES_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip() if raw.lstrip().startswith("#") else raw.strip()
        if not line:
            continue
        m = re.search(r"/pages/(\d+)", line) or re.fullmatch(r"(\d+)", line)
        if not m:
            raise SystemExit(f"pages.txt: can't find a page ID in line: {raw!r}")
        if m.group(1) not in ids:
            ids.append(m.group(1))
    return ids
