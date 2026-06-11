"""Tests del rendiment per nivell d'oponent (fcbillar.analytics)."""

from __future__ import annotations

import sqlite3

from fcbillar.analytics import (
    RATING_BUCKETS_TB,
    rating_breakdown,
    rating_breakdown_rows,
)
from fcbillar.db.migrations import ensure_schema


def _setup(tmp_path) -> tuple[sqlite3.Connection, int]:
    """BD mínima: jugador P contra 3 oponents amb nivells coneguts.

    - A: mitjana de rànquing 0,9 (via link)  → grup 0,800–1,000, P guanya
    - B: mitjana de rànquing 0,5 (via link)  → grup 0,400–0,600, P perd
    - C: sense link → fallback 18/30 = 0,6    → grup 0,600–0,800, P guanya
    """
    conn = ensure_schema(tmp_path / "t.db")
    conn.row_factory = sqlite3.Row
    tb = conn.execute("SELECT id FROM modalitats WHERE codi_fcb = 1").fetchone()["id"]

    def player(pid: int, nom: str) -> None:
        conn.execute("INSERT INTO players (id, fcb_id, nom) VALUES (?,?,?)", (pid, f"f{pid}", nom))

    for pid, nom in [(1, "P"), (2, "A"), (3, "B"), (4, "C")]:
        player(pid, nom)

    conn.execute(
        "INSERT INTO rankings (id, num_seq, modalitat_id, url, format_url) VALUES (1,1,?,?,?)",
        (tb, "u", "data"),
    )
    for player_id, mitjana in [(2, 0.9), (3, 0.5)]:
        conn.execute(
            "INSERT INTO ranking_entries (ranking_id, player_id, mitjana_general) VALUES (1,?,?)",
            (player_id, mitjana),
        )

    def game(gid: str, p2: int, c1: int, c2: int, winner: int) -> None:
        conn.execute(
            """INSERT INTO games (id, data_partida, modalitat_id, player1_id, player2_id,
                                  caramboles1, caramboles2, entrades, guanyador_id)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (gid, "2025-01-01", tb, 1, p2, c1, c2, 30, winner),
        )

    game("gA", 2, 40, 35, winner=1)  # P guanya A (rànquing 0,9)
    game("gB", 3, 30, 40, winner=3)  # P perd amb B (rànquing 0,5)
    game("gC", 4, 40, 18, winner=1)  # P guanya C (sense link → 18/30 = 0,6)

    # Links només per A i B (C cau al fallback de mitjana de partida).
    for gid, opp in [("gA", 2), ("gB", 3)]:
        conn.execute(
            "INSERT INTO ranking_game_links (ranking_id, game_id, player_id_origen) VALUES (1,?,?)",
            (gid, opp),
        )
    return conn, 1


def test_rating_breakdown_buckets_by_opponent_ranking(tmp_path) -> None:
    conn, pid = _setup(tmp_path)
    res = rating_breakdown(conn, 1, [pid])[pid]
    assert res["b0800"] == {"wins": 1, "losses": 0, "draws": 0}  # vs A (0,9)
    assert res["b0400"] == {"wins": 0, "losses": 1, "draws": 0}  # vs B (0,5)
    assert res["b0600"] == {"wins": 1, "losses": 0, "draws": 0}  # vs C (fallback 0,6)


def test_rating_breakdown_totals_reconcile(tmp_path) -> None:
    conn, pid = _setup(tmp_path)
    res = rating_breakdown(conn, 1, [pid])[pid]
    total = sum(b["wins"] + b["losses"] + b["draws"] for b in res.values())
    assert total == 3  # totes les partides de P queden classificades


def test_rating_breakdown_non_tres_bandes_is_empty(tmp_path) -> None:
    conn, pid = _setup(tmp_path)
    assert rating_breakdown(conn, 2, [pid]) == {}


def test_rating_breakdown_rows_fills_five_ordered_buckets(tmp_path) -> None:
    conn, pid = _setup(tmp_path)
    rows = rating_breakdown_rows(rating_breakdown(conn, 1, [pid]).get(pid))
    assert [r["bucket"] for r in rows] == [k for k, *_ in RATING_BUCKETS_TB]
    assert [r["bucket_order"] for r in rows] == [0, 1, 2, 3, 4]
    # Els grups buits surten a zero (no es perden eixos del radar).
    empty = next(r for r in rows if r["bucket"] == "ge1000")
    assert empty["wins"] == 0 and empty["losses"] == 0
