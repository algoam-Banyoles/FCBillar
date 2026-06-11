"""Importa les classificacions històriques de lliga (equips) per temporada.

Recorre l'Historial públic (no requereix login):

    /ca/historial → llistatLliga/{temp} → divisionsLliga/{lliga}
    → grupsLliga/{lliga}/{div} → classificacioLliga/{lliga}/{div}/{grup}

Punt clau (bug que arreglem): a `grupsLliga/{lliga}/{div}` cada fila de grup té
DOS enllaços —un a `jornadesLliga/{lliga}/{div}/{grup}` amb el NOM REAL del grup
("FINAL 1a DIVISIÓ", "GRUP A", "PROMOCIÓ-1"…) i, OPCIONALMENT, un botó
"Classificació" cap a `classificacioLliga/...`. L'scraper antic desava el text
del botó ("Classificació") com a nom de grup, de manera que la fase FINAL era
indistingible de les fases de grup. Aquí:

  1. Desem el NOM REAL del grup (de l'enllaç jornadesLliga).
  2. Construïm la URL de classificació directament des de l'id de grup, així
     capturem també fases FINAL que no mostren botó "Classificació".

Codificació: Playwright retorna `page.content()` ja descodificat i la caché es
llegeix/escriu en UTF-8 (client.py), de manera que el text arriba en Unicode
correcte. Parsegem sempre passant `str` a BeautifulSoup (mai `bytes`), perquè
lxml no torni a deduir cap codificació.

Desa a `lliga_standings_hist`
(temporada, lliga, divisio, grup, posicio, equip, pm, pp).
"""

from __future__ import annotations

import re
import sqlite3

from bs4 import BeautifulSoup

from fcbillar.config import get_settings
from fcbillar.scraper.client import ScraperClient

BASE = "https://www.fcbillar.cat"
# pos | equip | punts match | punts parcials  (l'equip pot dur números: "C.B. 2000 ...")
_ROW = re.compile(r"^(\d+)\s+(.+?)\s+(-?\d+)\s+(-?\d+)$")
_GRUP_ID = re.compile(r"jornadesLliga/\d+/\d+/(\d+)")


def _section(html: str) -> BeautifulSoup:
    """El contingut principal (`<section>`), sense l'`<aside>` de temporades ni el
    fil d'Ariadna —així no confonem enllaços de navegació amb els del contingut."""
    soup = BeautifulSoup(html, "lxml")
    return soup.select_one("section") or soup


def _links(node, pat):
    out = []
    for a in node.select("a"):
        h = a.get("href", "")
        if re.search(pat, h):
            out.append((h, a.get_text(strip=True)))
    return out


def parse_groups(html: str) -> list[tuple[int, str]]:
    """(grup_id, nom_real) de cada grup, des dels enllaços `jornadesLliga`."""
    out, seen = [], set()
    for href, text in _links(_section(html), r"jornadesLliga/\d+/\d+/\d+"):
        m = _GRUP_ID.search(href)
        if not m:
            continue
        gid = int(m.group(1))
        if gid in seen or not text:
            continue
        seen.add(gid)
        out.append((gid, text.strip()))
    return out


def parse_standings(html: str) -> list[tuple[int, str, int, int]]:
    out = []
    for d in _section(html).select("div.row"):
        m = _ROW.match(d.get_text(" ", strip=True))
        if m:
            out.append((int(m.group(1)), m.group(2).strip(), int(m.group(3)), int(m.group(4))))
    return out


def main():
    s = get_settings()
    conn = sqlite3.connect(str(s.db_path))
    # Taula NETA: purga les dades antigues (grup mal etiquetat com a "Classificació").
    conn.execute("DROP TABLE IF EXISTS lliga_standings_hist")
    conn.execute(
        "CREATE TABLE lliga_standings_hist "
        "(temporada TEXT, lliga TEXT, divisio TEXT, grup TEXT, posicio INTEGER, "
        "equip TEXT, pm INTEGER, pp INTEGER, "
        "PRIMARY KEY (temporada, lliga, divisio, grup, equip))"
    )
    conn.commit()
    total = 0
    with ScraperClient(s) as cl:
        hist = cl.fetch_html(f"{BASE}/ca/historial")
        seasons, seen_s = [], set()
        for surl, _ in _links(BeautifulSoup(hist, "lxml"), r"llistatLliga/\d"):
            season = surl.rstrip("/").split("/")[-1]
            if season not in seen_s:
                seen_s.add(season)
                seasons.append((season, surl))

        for season, surl in seasons:
            try:
                lst = cl.fetch_html(f"{BASE}/{surl.lstrip('/')}")
            except Exception:
                continue
            for dvurl, lliga_nom in _links(_section(lst), r"divisionsLliga/\d"):
                try:
                    dv = cl.fetch_html(f"{BASE}/{dvurl.lstrip('/')}")
                except Exception:
                    continue
                for gurl, div_nom in _links(_section(dv), r"grupsLliga/\d"):
                    try:
                        gp = cl.fetch_html(f"{BASE}/{gurl.lstrip('/')}")
                    except Exception:
                        continue
                    parts = gurl.rstrip("/").split("/")
                    lid, did = parts[-2], parts[-1]  # {lliga}/{div} de la pròpia URL
                    for gid, grup_nom in parse_groups(gp):
                        curl = f"{BASE}/ca/historial/classificacioLliga/{lid}/{did}/{gid}"
                        try:
                            ch = cl.fetch_html(curl)
                        except Exception:
                            continue  # fase sense classificació (p.ex. eliminatòria)
                        for pos, equip, pm, pp in parse_standings(ch):
                            conn.execute(
                                "INSERT OR REPLACE INTO lliga_standings_hist VALUES (?,?,?,?,?,?,?,?)",
                                (season, lliga_nom, div_nom, grup_nom, pos, equip, pm, pp),
                            )
                            total += 1
                        conn.commit()
            print(f"{season}: fet ({total} files acumulades)", flush=True)
    print(f"FET. files: {total}", flush=True)


if __name__ == "__main__":
    main()
