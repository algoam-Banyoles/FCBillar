"""Calcula rècords històrics i els publica a la taula fcbillar.records."""

from __future__ import annotations

import sqlite3

from fcbillar.cloud_sync import _upsert, get_client
from fcbillar.config import get_settings

NO3B = "AND UPPER(ti.nom) NOT LIKE '%FEMENI%' AND UPPER(ti.nom) NOT LIKE '%QUADRE%' " \
       "AND UPPER(ti.nom) NOT LIKE '%LLIURE%' AND UPPER(ti.nom) NOT LIKE '%BANDA %'"


def main() -> None:
    s = get_settings()
    conn = sqlite3.connect(str(s.db_path))
    conn.row_factory = sqlite3.Row
    rows = []

    def add(cat, q, fmt):
        for i, r in enumerate(conn.execute(q), start=1):
            rows.append({
                "categoria": cat, "ordre": i, "player_fcb_id": r["fcb"],
                "jugador": r["nom"], "valor": fmt(r), "detall": None,
            })

    add(
        "Millor mitjana (3 bandes)",
        """SELECT p.fcb_id fcb, p.nom, MAX(re.mitjana_general) v
        FROM ranking_entries re JOIN rankings rk ON rk.id=re.ranking_id
        JOIN modalitats m ON m.id=rk.modalitat_id JOIN players p ON p.id=re.player_id
        WHERE m.codi_fcb=1 AND p.fcb_id NOT LIKE 'name:%' GROUP BY p.id ORDER BY v DESC LIMIT 15""",
        lambda r: f"{r['v']:.3f}",
    )
    add(
        "Millor sèrie (3 bandes)",
        """SELECT p.fcb_id fcb, p.nom, MAX(x.s) v FROM (
            SELECT player1_id pid, serie_max1 s FROM games g JOIN modalitats m ON m.id=g.modalitat_id WHERE m.codi_fcb=1 AND serie_max1 IS NOT NULL
            UNION ALL SELECT player2_id, serie_max2 FROM games g JOIN modalitats m ON m.id=g.modalitat_id WHERE m.codi_fcb=1 AND serie_max2 IS NOT NULL
        ) x JOIN players p ON p.id=x.pid WHERE p.fcb_id NOT LIKE 'name:%' GROUP BY p.id ORDER BY v DESC LIMIT 15""",
        lambda r: str(r["v"]),
    )
    add(
        "Més partides (3 bandes)",
        """SELECT p.fcb_id fcb, p.nom, COUNT(*) v FROM (
            SELECT player1_id pid FROM games g JOIN modalitats m ON m.id=g.modalitat_id WHERE m.codi_fcb=1
            UNION ALL SELECT player2_id FROM games g JOIN modalitats m ON m.id=g.modalitat_id WHERE m.codi_fcb=1
        ) x JOIN players p ON p.id=x.pid WHERE p.fcb_id NOT LIKE 'name:%' GROUP BY p.id ORDER BY v DESC LIMIT 15""",
        lambda r: str(r["v"]),
    )
    add(
        "Opens guanyats (3 bandes)",
        f"""SELECT p.fcb_id fcb, p.nom, COUNT(*) v
        FROM torneig_participants tp JOIN torneigs_individuals ti ON ti.id=tp.torneig_id
        JOIN players p ON p.id=tp.player_id
        WHERE tp.posicio=1 AND UPPER(ti.nom) LIKE '%OPEN%' {NO3B} AND p.fcb_id NOT LIKE 'name:%'
        GROUP BY p.id ORDER BY v DESC LIMIT 15""",
        lambda r: str(r["v"]),
    )
    conn.close()

    sb = get_client()
    sb.table("records").delete().neq("categoria", "").execute()
    n = _upsert(sb, "records", rows, "categoria,ordre", lambda l, m: None)
    print(f"records publicats: {n} ({len(set(r['categoria'] for r in rows))} categories)")


if __name__ == "__main__":
    main()
