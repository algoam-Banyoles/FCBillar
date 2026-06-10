"""Recupera els encontres de lliga de temporades antigues (2014-2019), paral·lel.

Format historial (sense data a la pàgina):
  encontresLliga/{ll}/{dv}/{gp}/{jor}  →  partidesLliga/{ll}/{dv}/{gp}/{jor}/{enc}

Match directe: resol jugadors per nom i casa el game per (jugadors+caramboles+
entrades) dins del rang de dates de la temporada. Crea l'encontre (per etiquetar
3b/4mod) i assigna la sèrie. NO crea games ni toca modalitat/caramboles/entrades.
"""

from __future__ import annotations

import asyncio
import re
import sqlite3
import unicodedata

from playwright.async_api import async_playwright

from fcbillar.config import get_settings
from fcbillar.db.migrations import ensure_schema
from fcbillar.db.repository import Repository
from fcbillar.scraper.parsers import parse_lliga_partides

N_TABS = 6
OLD = ["2014-2015", "2015-2016", "2016-2017", "2017-2018", "2018-2019"]
BASE = "https://www.fcbillar.cat"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
ENC_RE = re.compile(r"partidesLliga/(\d+)/(\d+)/(\d+)/(\d+)/(\d+)")


def _nm(s):
    s = "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn")
    return " ".join(s.strip().lower().split())


def srange(s):
    y1, y2 = s.split("-")
    return (f"{y1}-08-01", f"{y2}-07-31")


def load(s):
    c = sqlite3.connect(f"file:{s.db_path}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    q = "SELECT DISTINCT encontre, temporada FROM lliga_player_clubs WHERE temporada IN (%s)" % ",".join("?" * len(OLD))
    jurls = [(r["encontre"], r["temporada"]) for r in c.execute(q, OLD)]
    done = {
        (r["lliga_id"], r["divisio_id"], r["grup_id"], r["encontre_id_extern"])
        for r in c.execute("SELECT lliga_id,divisio_id,grup_id,encontre_id_extern FROM encontres_lliga")
    }
    tmap = {r["nom"]: r["id"] for r in c.execute("SELECT id,nom FROM temporades")}
    pmap = {_nm(r["nom"]): r["id"] for r in c.execute("SELECT id,nom FROM players WHERE fcb_id NOT LIKE 'name:%'")}
    c.close()
    return jurls, done, tmap, pmap


async def worker(tab, ctx, queue, repo, done, tmap, pmap, state, emit):
    page = await ctx.new_page()
    while not state["dead"]:
        try:
            jurl, season = queue.get_nowait()
        except asyncio.QueueEmpty:
            break
        state["i"] += 1
        sr = srange(season)
        tid = tmap.get(season)
        try:
            await page.goto(f"{BASE}/{jurl.lstrip('/')}", wait_until="domcontentloaded", timeout=30000)
            encs = set(ENC_RE.findall(await page.content()))
            matched = 0
            for lg, dv, gp, jo, en in encs:
                lg, dv, gp, jo, en = int(lg), int(dv), int(gp), int(jo), int(en)
                if (lg, dv, gp, en) in done:
                    continue
                cur = repo.conn.execute(
                    "INSERT INTO encontres_lliga(lliga_id,divisio_id,grup_id,jornada_id,encontre_id_extern,temporada_id) "
                    "VALUES (?,?,?,?,?,?)",
                    (lg, dv, gp, jo, en, tid),
                )
                enc_id = cur.lastrowid
                done.add((lg, dv, gp, en))
                await page.goto(
                    f"{BASE}/ca/historial/partidesLliga/{lg}/{dv}/{gp}/{jo}/{en}",
                    wait_until="domcontentloaded", timeout=30000,
                )
                for row in parse_lliga_partides(await page.content()):
                    p1 = pmap.get(_nm(row.local_nom))
                    p2 = pmap.get(_nm(row.visitant_nom))
                    if not p1 or not p2:
                        continue
                    g = repo.conn.execute(
                        """SELECT id, player1_id FROM games WHERE data_partida BETWEEN ? AND ? AND entrades IS ?
                           AND ((player1_id=? AND player2_id=? AND caramboles1 IS ? AND caramboles2 IS ?)
                             OR (player1_id=? AND player2_id=? AND caramboles1 IS ? AND caramboles2 IS ?)) LIMIT 1""",
                        (sr[0], sr[1], row.entrades,
                         p1, p2, row.local_caramboles, row.visitant_caramboles,
                         p2, p1, row.visitant_caramboles, row.local_caramboles),
                    ).fetchone()
                    if not g:
                        continue
                    swapped = g["player1_id"] == p2
                    sa, sb = ((row.visitant_serie_major, row.local_serie_major) if swapped
                              else (row.local_serie_major, row.visitant_serie_major))
                    repo.conn.execute(
                        "UPDATE games SET encontre_lliga_id=COALESCE(encontre_lliga_id,?), "
                        "serie_max1=COALESCE(serie_max1,?), serie_max2=COALESCE(serie_max2,?) WHERE id=?",
                        (enc_id, sa, sb, g["id"]),
                    )
                    matched += 1
            repo.conn.commit()
            state["ok"] += 1
            state["consec"] = 0
            emit(f"[{state['i']}/{state['total']}] T{tab} {season} jor{jurl.split('/')[-1]} → {matched} enllaçats")
        except Exception:  # noqa: BLE001
            state["err"] += 1
            state["consec"] += 1
            emit(f"[{state['i']}/{state['total']}] T{tab} → (error)")
            if state["consec"] >= 40:
                state["dead"] = True
                emit("⚠️  Massa errors seguits — atura.")
    await page.close()


async def main():
    s = get_settings()
    jurls, done, tmap, pmap = load(s)
    total = len(jurls)
    logf = open(s.db_path.parent / "old_lliga_progress.log", "a", encoding="utf-8")

    def emit(m):
        print(m, flush=True)
        logf.write(m + "\n")
        logf.flush()

    emit(f"=== OLD LLIGA ({N_TABS} tabs) · jornades: {total} ===")
    queue: asyncio.Queue = asyncio.Queue()
    for j in jurls:
        queue.put_nowait(j)
    conn = ensure_schema(s.db_path)
    repo = Repository(conn)
    state = {"i": 0, "ok": 0, "err": 0, "consec": 0, "total": total, "dead": False}
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        ctx = await b.new_context(storage_state=str(s.storage_state_path), user_agent=UA, locale="ca-ES")
        await asyncio.gather(*[worker(t + 1, ctx, queue, repo, done, tmap, pmap, state, emit) for t in range(N_TABS)])
        await b.close()
    emit(f"=== FET ({state['ok']} ok / {state['err']} err de {total}) ===")
    logf.close()
    conn.close()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        N_TABS = int(sys.argv[1])
    asyncio.run(main())
