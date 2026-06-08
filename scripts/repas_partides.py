"""Repàs complet de partides: rànquing a rànquing, jugador a jugador.

El portal només exposa la finestra de partides d'un jugador EN un rànquing
concret, així que per recuperar tot l'historial cal cridar partideshome per
cada (rànquing, jugador). Idempotent (dedup per id_natural) i resumible
(saltem els (rànquing, jugador) que ja tenen partides enllaçades).
"""

from __future__ import annotations

import sqlite3

from fcbillar.config import get_settings
from fcbillar.pipeline import ingest_partides
from fcbillar.scraper.client import ScraperClient


def main() -> None:
    s = get_settings()
    conn = sqlite3.connect(str(s.db_path))
    conn.row_factory = sqlite3.Row

    done = {
        (r["ranking_id"], r["player_id_origen"])
        for r in conn.execute("SELECT DISTINCT ranking_id, player_id_origen FROM ranking_game_links")
    }
    combos = [
        (r["num"], r["mod"], r["fcb"])
        for r in conn.execute(
            """
            SELECT rk.num_seq AS num, m.codi_fcb AS mod, p.fcb_id AS fcb,
                   re.ranking_id AS rid, re.player_id AS pid
            FROM ranking_entries re
            JOIN rankings rk ON rk.id = re.ranking_id
            JOIN modalitats m ON m.id = rk.modalitat_id
            JOIN players p ON p.id = re.player_id
            WHERE p.fcb_id NOT LIKE 'name:%'
            ORDER BY rk.num_seq DESC, m.codi_fcb, p.fcb_id
            """
        )
        if (r["rid"], r["pid"]) not in done
    ]
    conn.close()

    total = len(combos)
    print(f"combos pendents: {total}", flush=True)
    ok = err = consec = 0

    def _new_client():
        cl = ScraperClient(s)
        cl.__enter__()
        return cl

    cl = _new_client()
    try:
        for i, (num, mod, fcb) in enumerate(combos, 1):
            try:
                ingest_partides(cl, num, mod, fcb, settings=s, create_missing_players=True)
                ok += 1
                consec = 0
            except Exception:  # noqa: BLE001
                err += 1
                consec += 1
            # Refresca la sessió periòdicament o si hi ha molts errors seguits
            # (símptoma de sessió morta a mig camí).
            if i % 1500 == 0 or consec == 30:
                cl.__exit__(None, None, None)
                cl = _new_client()
                consec = 0
            if i % 250 == 0:
                print(f"  {i}/{total} (ok={ok} err={err})", flush=True)
    finally:
        cl.__exit__(None, None, None)
    print(f"FET ({ok}/{total}, err={err})", flush=True)


if __name__ == "__main__":
    main()
