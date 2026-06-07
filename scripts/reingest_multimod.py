"""Re-ingesta de les lligues multi-modalitat (4 modalitats / Catalana) per
corregir la modalitat per-partida (bug: tot l'encontre s'etiquetava amb una
sola modalitat). Itera els grups ja coneguts a la BD i els torna a ingerir amb
el parser corregit. La dedup dels duplicats erronis es fa després, a part.
"""

from __future__ import annotations

import sqlite3

from fcbillar.config import get_settings
from fcbillar.pipeline import ingest_lliga_grup
from fcbillar.scraper.client import ScraperClient

# Lligues etiquetades majoritàriament "Lliure" = multi-modalitat (37 ja fet).
LEAGUES = [3, 7, 9, 13, 18, 22, 25, 27, 31, 33, 35]


def main() -> None:
    s = get_settings()
    conn = sqlite3.connect(str(s.db_path))
    conn.row_factory = sqlite3.Row
    groups: list[tuple[int, int, int]] = []
    for lliga in LEAGUES:
        for r in conn.execute(
            "SELECT DISTINCT divisio_id, grup_id FROM encontres_lliga WHERE lliga_id=? ORDER BY divisio_id, grup_id",
            (lliga,),
        ):
            groups.append((lliga, r["divisio_id"], r["grup_id"]))
    conn.close()
    print(f"Grups a re-ingerir: {len(groups)}", flush=True)

    with ScraperClient(s) as client:
        for i, (lliga, divisio, grup) in enumerate(groups, 1):
            try:
                res = ingest_lliga_grup(
                    client,
                    lliga_id=lliga,
                    divisio_id=divisio,
                    grup_id=grup,
                    modalitat_codi_fcb=2,  # fallback; la modalitat real ve per-partida
                    settings=s,
                )
                print(
                    f"[{i}/{len(groups)}] {lliga}/{divisio}/{grup}: "
                    f"{res.total_encontres} enc, {res.total_games_upserted} partides",
                    flush=True,
                )
            except Exception as e:  # noqa: BLE001
                print(f"[{i}/{len(groups)}] {lliga}/{divisio}/{grup}: ERROR {e}", flush=True)
    print("FET re-ingesta", flush=True)


if __name__ == "__main__":
    main()
