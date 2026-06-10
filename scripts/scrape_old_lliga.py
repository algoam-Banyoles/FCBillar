"""Re-enllaça la lliga de 2014-2019 (síncron, robust).

El relink recent va usar /lligues/partides/ (format recent) i no va casar les
temporades velles, que són a /historial/partidesLliga/. Aquí, per cada jornada
de lliga_player_clubs (2014-2019), es descobreixen els encontres, es crea
l'encontre si falta i es CASA cada partida amb el game existent per
(jugadors + caramboles + entrades) dins del rang de dates de la temporada
(les pàgines historial no porten data), assignant encontre + sèrie.
Idempotent (COALESCE) i resumible.
"""

from __future__ import annotations

import re
import sqlite3
import time
import unicodedata

from fcbillar.config import get_settings
from fcbillar.scraper.client import ScraperClient
from fcbillar.scraper.parsers import parse_lliga_partides

# 2014-2015 ja està enllaçat de l'scrape original; ataquem el forat 2015-2019.
OLD = ["2015-2016", "2016-2017", "2017-2018", "2018-2019"]
BASE = "https://www.fcbillar.cat"
ENC_RE = re.compile(r"partidesLliga/(\d+)/(\d+)/(\d+)/(\d+)/(\d+)")


def _nm(s):
    s = "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn")
    return " ".join(s.strip().lower().split())


def srange(s):
    y1, y2 = s.split("-")
    return (f"{y1}-08-01", f"{y2}-07-31")


def main():
    s = get_settings()
    conn = sqlite3.connect(str(s.db_path))
    conn.row_factory = sqlite3.Row
    pmap = {_nm(r["nom"]): r["id"] for r in conn.execute("SELECT id,nom FROM players WHERE fcb_id NOT LIKE 'name:%'")}
    encmap = {
        (r["lliga_id"], r["divisio_id"], r["grup_id"], r["encontre_id_extern"]): r["id"]
        for r in conn.execute("SELECT id,lliga_id,divisio_id,grup_id,encontre_id_extern FROM encontres_lliga")
    }
    tmap = {r["nom"]: r["id"] for r in conn.execute("SELECT id,nom FROM temporades")}
    q = "SELECT DISTINCT encontre, temporada FROM lliga_player_clubs WHERE temporada IN (%s) ORDER BY temporada" % ",".join("?" * len(OLD))
    jornades = [(r["encontre"], r["temporada"]) for r in conn.execute(q, OLD)]

    logf = open(s.db_path.parent / "old_lliga_progress.log", "a", encoding="utf-8")

    def emit(m):
        print(m, flush=True)
        logf.write(m + "\n")
        logf.flush()

    total = len(jornades)
    emit(f"=== OLD LLIGA (síncron) · jornades: {total} ===")
    linked = encs_new = consec = 0

    def _client():
        cl = ScraperClient(s)
        cl.__enter__()
        return cl

    cl = _client()
    try:
        for i, (jurl, season) in enumerate(jornades, 1):
            r0 = srange(season)
            tid = tmap.get(season)
            try:
                html = cl.fetch_html(f"{BASE}/{jurl.lstrip('/')}", use_cache=False)
                encs = set(ENC_RE.findall(html))
                jl = 0
                for lg, dv, gp, jo, en in encs:
                    lg, dv, gp, jo, en = int(lg), int(dv), int(gp), int(jo), int(en)
                    key = (lg, dv, gp, en)
                    enc_id = encmap.get(key)
                    if enc_id is None:
                        # equips 0 = placeholder (NOT NULL; FK desactivada). El que
                        # importa és lliga_id (etiqueta 3b/4mod) + la sèrie; els games
                        # no referencien els equips de l'encontre.
                        enc_id = conn.execute(
                            "INSERT INTO encontres_lliga(lliga_id,divisio_id,grup_id,jornada_id,encontre_id_extern,temporada_id,equip_local_id,equip_visitant_id) "
                            "VALUES (?,?,?,?,?,?,0,0)", (lg, dv, gp, jo, en, tid),
                        ).lastrowid
                        encmap[key] = enc_id
                        encs_new += 1
                    ph = cl.fetch_html(f"{BASE}/ca/historial/partidesLliga/{lg}/{dv}/{gp}/{jo}/{en}", use_cache=False)
                    for row in parse_lliga_partides(ph):
                        p1 = pmap.get(_nm(row.local_nom))
                        p2 = pmap.get(_nm(row.visitant_nom))
                        if not p1 or not p2:
                            continue
                        g = conn.execute(
                            """SELECT id, player1_id FROM games WHERE data_partida BETWEEN ? AND ? AND entrades IS ?
                               AND ((player1_id=? AND player2_id=? AND caramboles1 IS ? AND caramboles2 IS ?)
                                 OR (player1_id=? AND player2_id=? AND caramboles1 IS ? AND caramboles2 IS ?)) LIMIT 1""",
                            (r0[0], r0[1], row.entrades,
                             p1, p2, row.local_caramboles, row.visitant_caramboles,
                             p2, p1, row.visitant_caramboles, row.local_caramboles),
                        ).fetchone()
                        if not g:
                            continue
                        sw = g["player1_id"] == p2
                        sa, sb = ((row.visitant_serie_major, row.local_serie_major) if sw
                                  else (row.local_serie_major, row.visitant_serie_major))
                        conn.execute(
                            "UPDATE games SET encontre_lliga_id=COALESCE(encontre_lliga_id,?), "
                            "serie_max1=COALESCE(serie_max1,?), serie_max2=COALESCE(serie_max2,?) WHERE id=?",
                            (enc_id, sa, sb, g["id"]),
                        )
                        jl += 1
                conn.commit()
                linked += jl
                consec = 0
                if i % 25 == 0 or jl:
                    emit(f"[{i}/{total}] {season} jor{jurl.split('/')[-1]} → {jl} enllaçats (total {linked}, encs nous {encs_new})")
            except Exception as e:  # noqa: BLE001
                consec += 1
                emit(f"[{i}/{total}] {season} → error: {str(e)[:40]}")
                if consec in (15, 30):
                    emit("   refrescant client…")
                    cl.__exit__(None, None, None)
                    time.sleep(10)
                    cl = _client()
                if consec >= 60:
                    emit("⚠️  Sessió morta? Re-logina i torna a llançar (resumeix).")
                    break
            time.sleep(0.15)
    finally:
        cl.__exit__(None, None, None)
    emit(f"=== FET. enllaçats {linked}, encontres nous {encs_new} ===")
    logf.close()
    conn.close()


if __name__ == "__main__":
    main()
