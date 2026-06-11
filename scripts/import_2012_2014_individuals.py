"""Importa els campionats individuals agregats de l'historial 2012-2014.

La Federació publica les partides de quatre modalitats, però no en publica ni
la classificació final ni la categoria/divisió. Totes provenen de la pàgina
històrica d'individuals 2012-2014 i, per tant, es cataloguen explícitament com
a Campionat de Catalunya sense inventar una categoria concreta.
"""

from __future__ import annotations

import sqlite3
import unicodedata

from fcbillar.config import get_settings

SEASON = "2012-2014"

# torneig extern -> (divisió agregada, codi FCB de modalitat, nom canònic)
COMPETITIONS = {
    11: (30, 1, "CAMPIONAT CATALUNYA HISTÒRIC 3 BANDES - CATEGORIA NO PUBLICADA"),
    12: (31, 4, "CAMPIONAT CATALUNYA HISTÒRIC BANDA - CATEGORIA NO PUBLICADA"),
    13: (32, 2, "CAMPIONAT CATALUNYA HISTÒRIC LLIURE - CATEGORIA NO PUBLICADA"),
    14: (33, 3, "CAMPIONAT CATALUNYA HISTÒRIC QUADRE 47/2 - CATEGORIA NO PUBLICADA"),
}


def _normalize_name(value: str) -> str:
    plain = "".join(
        char
        for char in unicodedata.normalize("NFD", value or "")
        if unicodedata.category(char) != "Mn"
    )
    return " ".join(plain.strip().lower().split())


def main() -> None:
    settings = get_settings()
    conn = sqlite3.connect(str(settings.db_path))
    conn.row_factory = sqlite3.Row

    season = conn.execute("SELECT id FROM temporades WHERE nom=?", (SEASON,)).fetchone()
    if season is None:
        conn.execute("INSERT INTO temporades(nom) VALUES (?)", (SEASON,))
        season_id = conn.execute("SELECT id FROM temporades WHERE nom=?", (SEASON,)).fetchone()[0]
    else:
        season_id = season["id"]

    modality_ids = {
        row["codi_fcb"]: row["id"]
        for row in conn.execute("SELECT id, codi_fcb FROM modalitats")
    }
    players = {
        _normalize_name(row["nom"]): row["id"]
        for row in conn.execute("SELECT id, nom FROM players")
    }

    for tournament_id, (division_id, modality_code, name) in COMPETITIONS.items():
        conn.execute(
            """
            INSERT INTO torneigs_individuals(
                torneig_id_extern, divisio_id_extern, nom, modalitat_id, temporada_id
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(torneig_id_extern, divisio_id_extern, temporada_id)
            DO UPDATE SET nom=excluded.nom, modalitat_id=excluded.modalitat_id
            """,
            (tournament_id, division_id, name, modality_ids[modality_code], season_id),
        )
        local_id = conn.execute(
            """
            SELECT id FROM torneigs_individuals
            WHERE torneig_id_extern=? AND divisio_id_extern=? AND temporada_id=?
            """,
            (tournament_id, division_id, season_id),
        ).fetchone()[0]

        names = {
            row[0]
            for row in conn.execute(
                """
                SELECT player1_nom FROM torneig_partides
                WHERE torneig_id_extern=? AND divisio_id_extern=?
                UNION
                SELECT player2_nom FROM torneig_partides
                WHERE torneig_id_extern=? AND divisio_id_extern=?
                """,
                (tournament_id, division_id, tournament_id, division_id),
            )
        }
        for player_name in sorted(names):
            key = _normalize_name(player_name)
            player_id = players.get(key)
            if player_id is None:
                fcb_id = f"name:{key}"
                conn.execute(
                    """
                    INSERT OR IGNORE INTO players(fcb_id, nom, created_at, updated_at)
                    VALUES (?, ?, datetime('now'), datetime('now'))
                    """,
                    (fcb_id, player_name),
                )
                player_id = conn.execute(
                    "SELECT id FROM players WHERE fcb_id=?", (fcb_id,)
                ).fetchone()[0]
                players[key] = player_id
            conn.execute(
                """
                INSERT OR IGNORE INTO torneig_participants(torneig_id, player_id)
                VALUES (?, ?)
                """,
                (local_id, player_id),
            )
        conn.commit()
        print(f"{tournament_id}/{division_id}: {len(names)} jugadors", flush=True)

    conn.close()


if __name__ == "__main__":
    main()
