"""Recupera les categories/divisions dels torneigs individuals històrics.

La classificació final només identifica la divisió per id. La pàgina
`individuals/divisions/{torneig_id}` és la font que relaciona aquest id amb
HONOR, 1A DIVISIÓ, etc. Aquest script torna a consultar aquestes pàgines i
enriqueix els noms locals abans de republicar-los a Supabase.
"""

from __future__ import annotations

import sqlite3

from fcbillar.config import get_settings
from fcbillar.scraper.client import ScraperClient
from fcbillar.scraper.parsers import parse_individuals_divisions


def main() -> None:
    settings = get_settings()
    conn = sqlite3.connect(str(settings.db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, torneig_id_extern, divisio_id_extern, nom
        FROM torneigs_individuals
        ORDER BY torneig_id_extern, divisio_id_extern
        """
    ).fetchall()
    by_tournament: dict[int, list[sqlite3.Row]] = {}
    for row in rows:
        by_tournament.setdefault(row["torneig_id_extern"], []).append(row)

    updated = 0
    missing = 0
    base = settings.base_url.rstrip("/")
    with ScraperClient(settings) as client:
        for index, (tournament_id, tournament_rows) in enumerate(by_tournament.items(), start=1):
            url = f"{base}/ca/individuals/divisions/{tournament_id}"
            try:
                html = client.fetch_html(url, use_cache=False)
                divisions = {
                    d.divisio_id_extern: d.nom.strip().upper()
                    for d in parse_individuals_divisions(html)
                }
            except Exception as exc:  # noqa: BLE001
                print(f"[{index}/{len(by_tournament)}] {tournament_id}: ERROR {exc}", flush=True)
                missing += len(tournament_rows)
                continue

            for row in tournament_rows:
                category = divisions.get(row["divisio_id_extern"])
                if not category:
                    missing += 1
                    continue
                old_name = row["nom"].strip()
                base_name = old_name.split(" - ", 1)[0].strip()
                new_name = base_name if category in {"UNICA", "ÚNICA"} else f"{base_name} - {category}"
                if new_name != old_name:
                    conn.execute(
                        "UPDATE torneigs_individuals SET nom=? WHERE id=?",
                        (new_name, row["id"]),
                    )
                    updated += 1
            conn.commit()
            print(
                f"[{index}/{len(by_tournament)}] {tournament_id}: "
                f"{len(divisions)} categories",
                flush=True,
            )

    conn.close()
    print(f"updated={updated} missing={missing}")


if __name__ == "__main__":
    main()
