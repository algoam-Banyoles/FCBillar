"""Corregeix mitjanes de rànquing errònies contrastant amb les partides.

La mitjana d'una entrada de rànquing (FCB) ha de ser caramboles/entrades de les
partides d'aquell jugador en aquella finestra. Quan la FCB infracompta les
entrades (p.ex. 3 en comptes de 34 → mitjana inflada), les partides (l'altra
font FCB) ho revelen. Si les partides cobreixen la finestra (prou entrades) i en
tenen força més que les que diu la FCB, recalculem la mitjana des de les partides.
"""

from __future__ import annotations

import json
import sqlite3

from fcbillar.config import get_settings


def main() -> None:
    s = get_settings()
    c = sqlite3.connect(str(s.db_path))
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA busy_timeout=20000")
    rows = c.execute(
        """SELECT re.id, re.player_id pid, re.ranking_id rid, re.mitjana_general mg, re.extras_json ex
           FROM ranking_entries re WHERE re.mitjana_general IS NOT NULL AND re.extras_json IS NOT NULL"""
    ).fetchall()
    fixed = []
    for r in rows:
        ex = json.loads(r["ex"])
        fcb_ent = ex.get("entrades")
        if not fcb_ent:
            continue
        gs = c.execute(
            """SELECT CASE WHEN g.player1_id=? THEN g.caramboles1 ELSE g.caramboles2 END car, g.entrades ent
               FROM ranking_game_links rgl JOIN games g ON g.id=rgl.game_id
               WHERE rgl.ranking_id=? AND rgl.player_id_origen=?""",
            (r["pid"], r["rid"], r["pid"]),
        ).fetchall()
        se = sum(x["ent"] or 0 for x in gs)
        sc = sum(x["car"] or 0 for x in gs)
        # Partides fiables (>=10 entrades) i FCB n'infracompta força (>1.5x menys).
        if se >= 10 and se > fcb_ent * 1.5 and sc:
            gm = round(sc / se, 5)
            if abs(gm - r["mg"]) > 0.5:
                c.execute("UPDATE ranking_entries SET mitjana_general=? WHERE id=?", (gm, r["id"]))
                fixed.append((r["id"], r["mg"], gm, fcb_ent, se))
    c.commit()
    print(f"corregides {len(fixed)} entrades de ranquing")
    for _id, old, new, fe, ge in fixed[:20]:
        print(f"  id {_id}: {old} -> {new}  (FCB ent {fe} vs partides ent {ge})")
    c.close()


if __name__ == "__main__":
    main()
