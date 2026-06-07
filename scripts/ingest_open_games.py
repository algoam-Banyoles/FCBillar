"""Ingest dels resultats reals (partides) dels opens/campionats individuals.

Recorre cada (torneig, divisió), llegeix la pàgina de fases, en treu les URLs
d'eliminatòria i parseja cada partit (jugadors + caramboles + entrades). Desa a
`torneig_partides`. Els resultats de la fase de grups NO surten a la web (només
composició), així que es capturen les eliminatòries (la part principal).
"""

from __future__ import annotations

import re
import sqlite3

from bs4 import BeautifulSoup

from fcbillar.config import get_settings
from fcbillar.scraper.client import ScraperClient

BASE = "https://www.fcbillar.cat"


def _parse_player(txt: str):
    m = re.match(r"^(.*?)\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\s*$", txt)
    if not m:
        return None
    return (m.group(1).strip(), int(m.group(2)), int(m.group(3)), int(m.group(4)))


def parse_partides(html: str):
    soup = BeautifulSoup(html, "lxml")
    out = []
    for box in soup.select("div.row.box.black"):
        sibs = []
        sib = box
        for _ in range(3):
            sib = sib.find_next_sibling("div")
            if sib is None:
                break
            sibs.append(sib)
        if len(sibs) < 3:
            continue
        p1 = _parse_player(sibs[0].get_text(" ", strip=True))
        p2 = _parse_player(sibs[1].get_text(" ", strip=True))
        em = re.search(r"Entrades:\s*(\d+)", sibs[2].get_text(" ", strip=True))
        if not p1 or not p2:
            continue
        out.append({
            "p1": p1[0], "punts1": p1[1], "serie1": p1[2], "car1": p1[3],
            "p2": p2[0], "punts2": p2[1], "serie2": p2[2], "car2": p2[3],
            "entrades": int(em.group(1)) if em else None,
        })
    return out


def main() -> None:
    s = get_settings()
    conn = sqlite3.connect(str(s.db_path))
    conn.row_factory = sqlite3.Row
    opens = conn.execute(
        "SELECT DISTINCT torneig_id_extern, divisio_id_extern FROM torneigs_individuals"
    ).fetchall()
    conn.execute("DELETE FROM torneig_partides")
    conn.commit()
    total = 0
    with ScraperClient(s) as cl:
        for i, o in enumerate(opens, 1):
            t, d = o["torneig_id_extern"], o["divisio_id_extern"]
            try:
                fases_html = cl.fetch_html(f"{BASE}/ca/individuals/fases/{t}/{d}")
            except Exception as e:  # noqa: BLE001
                print(f"[{i}/{len(opens)}] {t}/{d}: FAIL fases {e}", flush=True)
                continue
            soup = BeautifulSoup(fases_html, "lxml")
            elim = []
            for a in soup.select("a"):
                h = a.get("href", "")
                m = re.search(r"partideseliminatoria/(\d+)/(\d+)/(\d+)", h)
                if m:
                    elim.append(int(m.group(3)))
            n = 0
            for fase_id in sorted(set(elim)):
                try:
                    html = cl.fetch_html(
                        f"{BASE}/ca/individuals/partideseliminatoria/{t}/{d}/{fase_id}"
                    )
                except Exception:  # noqa: BLE001
                    continue
                for g in parse_partides(html):
                    conn.execute(
                        """INSERT INTO torneig_partides
                        (torneig_id_extern, divisio_id_extern, fase_id,
                         player1_nom, caramboles1, serie1, punts1,
                         player2_nom, caramboles2, serie2, punts2, entrades)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (t, d, fase_id, g["p1"], g["car1"], g["serie1"], g["punts1"],
                         g["p2"], g["car2"], g["serie2"], g["punts2"], g["entrades"]),
                    )
                    n += 1
            conn.commit()
            total += n
            print(f"[{i}/{len(opens)}] {t}/{d}: {n} partides", flush=True)
    print(f"FET. total partides: {total}", flush=True)


if __name__ == "__main__":
    main()
