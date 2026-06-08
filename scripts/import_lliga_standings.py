"""Importa les classificacions històriques de lliga (equips) per temporada.

historial → llistatLliga/{temp} → divisionsLliga/{lliga} → grupsLliga/{lliga}/{div}
→ classificacioLliga/{lliga}/{div}/{grup}  (pos | equip | punts match | punts parcials)
Desa a lliga_standings_hist (temporada, lliga, divisio, grup, posicio, equip, pm, pp).
"""

from __future__ import annotations

import re
import sqlite3

from bs4 import BeautifulSoup

from fcbillar.config import get_settings
from fcbillar.scraper.client import ScraperClient

BASE = "https://www.fcbillar.cat"
_ROW = re.compile(r"^(\d+)\s+(.+?)\s+(-?\d+)\s+(-?\d+)$")


def _links(html, pat):
    out = []
    for a in BeautifulSoup(html, "lxml").select("a"):
        h = a.get("href", "")
        if re.search(pat, h):
            out.append((h, a.get_text(strip=True)))
    return out


def parse_standings(html):
    out = []
    for d in BeautifulSoup(html, "lxml").select("div.row"):
        m = _ROW.match(d.get_text(" ", strip=True))
        if m:
            out.append((int(m.group(1)), m.group(2).strip(), int(m.group(3)), int(m.group(4))))
    return out


def main():
    s = get_settings()
    conn = sqlite3.connect(str(s.db_path))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS lliga_standings_hist "
        "(temporada TEXT, lliga TEXT, divisio TEXT, grup TEXT, posicio INTEGER, "
        "equip TEXT, pm INTEGER, pp INTEGER, PRIMARY KEY (temporada, lliga, divisio, grup, equip))"
    )
    conn.commit()
    total = 0
    with ScraperClient(s) as cl:
        hist = cl.fetch_html(f"{BASE}/ca/historial")
        for surl, _ in _links(hist, r"llistatLliga/\d"):
            season = surl.rstrip("/").split("/")[-1]
            try:
                lst = cl.fetch_html(f"{BASE}/{surl.lstrip('/')}")
            except Exception:  # noqa: BLE001
                continue
            for dvurl, lliga_nom in _links(lst, r"divisionsLliga/\d"):
                try:
                    dv = cl.fetch_html(f"{BASE}/{dvurl.lstrip('/')}")
                except Exception:  # noqa: BLE001
                    continue
                for gurl, div_nom in _links(dv, r"grupsLliga/\d"):
                    try:
                        gp = cl.fetch_html(f"{BASE}/{gurl.lstrip('/')}")
                    except Exception:  # noqa: BLE001
                        continue
                    for curl, grup_nom in _links(gp, r"classificacioLliga/\d"):
                        try:
                            ch = cl.fetch_html(f"{BASE}/{curl.lstrip('/')}")
                        except Exception:  # noqa: BLE001
                            continue
                        for pos, equip, pm, pp in parse_standings(ch):
                            conn.execute(
                                "INSERT OR REPLACE INTO lliga_standings_hist VALUES (?,?,?,?,?,?,?,?)",
                                (season, lliga_nom, div_nom, grup_nom or "", pos, equip, pm, pp),
                            )
                            total += 1
                        conn.commit()
            print(f"{season}: fet ({total} files)", flush=True)
    print(f"FET. files: {total}", flush=True)


if __name__ == "__main__":
    main()
