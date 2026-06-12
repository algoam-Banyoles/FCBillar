"""Tests del rànquing del Circuit Català Tres Bandes Femení."""

from __future__ import annotations

import sqlite3

import pytest

from fcb_opens.reglament.puntuacio import points_for_position_femeni
from fcbillar.db.migrations import ensure_schema
from fcbillar.opens_femeni import femeni_ranking_rows


def test_points_table_campionat_vs_open() -> None:
    # Article XVI: el Campionat puntua més alt que els Opens.
    assert points_for_position_femeni(1, is_campionat=True) == 150
    assert points_for_position_femeni(1, is_campionat=False) == 100
    assert points_for_position_femeni(5, is_campionat=True) == 70
    assert points_for_position_femeni(12, is_campionat=False) == 14


def test_points_floor_beyond_table() -> None:
    # Més enllà de la 12a posició s'aplica el valor de la 12a (camps petits).
    assert points_for_position_femeni(20, is_campionat=False) == 14
    assert points_for_position_femeni(99, is_campionat=True) == 38


def test_points_invalid_position() -> None:
    with pytest.raises(ValueError):
        points_for_position_femeni(0, is_campionat=True)


def _setup(tmp_path) -> sqlite3.Connection:
    """Dues proves: un Campionat (div 10) i un Open (div 20)."""
    conn = ensure_schema(tmp_path / "t.db")
    conn.row_factory = sqlite3.Row
    for pid, nom in [(1, "A"), (2, "B"), (3, "C")]:
        conn.execute("INSERT INTO players (id, fcb_id, nom) VALUES (?,?,?)", (pid, f"f{pid}", nom))
    conn.execute(
        "INSERT INTO torneigs_individuals (id, torneig_id_extern, divisio_id_extern, nom) "
        "VALUES (1, 100, 10, 'TRES BANDES FEMENI')"
    )
    conn.execute(
        "INSERT INTO torneigs_individuals (id, torneig_id_extern, divisio_id_extern, nom) "
        "VALUES (2, 100, 20, 'OPEN FEMENI TRES BANDES X')"
    )

    def part(tid: int, pid: int, pos: int) -> None:
        conn.execute(
            "INSERT INTO torneig_participants (torneig_id, player_id, posicio) VALUES (?,?,?)",
            (tid, pid, pos),
        )

    # Campionat (150/120): A 1r, B 2n.  Open (100/80/60): B 1r, A 2n, C 3r.
    part(1, 1, 1)
    part(1, 2, 2)
    part(2, 2, 1)
    part(2, 1, 2)
    part(2, 3, 3)
    return conn


def test_femeni_ranking_applies_correct_tables_and_order(tmp_path) -> None:
    rows = femeni_ranking_rows(_setup(tmp_path))
    max_ronda = max(r["ronda"] for r in rows)
    current = sorted((r for r in rows if r["ronda"] == max_ronda), key=lambda r: r["posicio"])
    # A: campionat 1r (150) + open 2n (80) = 230 → 1a
    # B: campionat 2n (120) + open 1r (100) = 220 → 2a
    # C: open 3r (60) = 60 → 3a
    assert [(r["jugador"], r["punts"]) for r in current] == [("A", 230), ("B", 220), ("C", 60)]
    assert current[0]["opens_jugats"] == 2


def test_femeni_ranking_empty_without_provas(tmp_path) -> None:
    conn = ensure_schema(tmp_path / "empty.db")
    conn.row_factory = sqlite3.Row
    assert femeni_ranking_rows(conn) == []
