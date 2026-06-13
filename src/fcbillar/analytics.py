"""Anàlisi derivada: rendiment d'un jugador per nivell de l'oponent.

Per a la fitxa de jugador volem un gràfic "aranya" amb victòries i derrotes
contra oponents agrupats pel **nivell de rànquing en el moment de disputar la
partida**. Les branques **s'adapten al perfil del jugador**: un nombre fix de
branques (N_BRANCHES) d'igual amplada que reparteixen el rang real de rivals que
ha trobat (del més fluix al més fort). Així un jugador d'1,0+ veu la resolució a
dalt (1,1/1,2/1,3) i un de 0,5 veu fines les seves franges, en lloc d'una graella
fixa que els amaga.

Definició de la "mitjana de rànquing de l'oponent en aquell moment" (per cada
partida + oponent O):

1. **Primari** — la `mitjana_general` d'O al snapshot on la partida entra a la
   finestra de rànquing: la fila de `ranking_game_links` d'O per aquesta partida
   amb el `num_seq` mínim. És la mateixa relació que fa servir `player_games`.
2. **Fallback** — si O no té cap link per aquesta partida, la mitjana de la
   pròpia partida (`caramboles_oponent / entrades`).
3. Si no hi ha cap de les dues, la partida no es classifica.

A més es calculen dos indicadors (només partides decisives):
  - `weighted_index`: % de victòries ponderat pel nivell del rival (guanyar forts
    compta més). 100 · Σ_victòries r / Σ_decisives r.
  - `crossover`: nivell de rival on la taxa de victòries creua el 50% ("ets
    competitiu fins a ~X"), interpolat sobre les branques.

De moment només Tres bandes (codi_fcb = 1).
"""

from __future__ import annotations

import sqlite3
from itertools import pairwise

N_BRANCHES = 6  # nombre fix de branques de l'aranya (adaptatives per jugador)


def _fmt(v: float) -> str:
    """Format d'un valor de mitjana per a etiqueta (coma decimal, 2 decimals)."""
    return f"{v:.2f}".replace(".", ",")


def _adaptive_buckets(games: list[tuple[int, float]]) -> list[dict]:
    """Reparteix les partides en N_BRANCHES franges d'igual amplada sobre el rang
    [min, max] de mitjanes de rival observades. `games` = llista de (res, rating)
    on res ∈ {1 victòria, -1 derrota, 0 empat}. Retorna sempre N_BRANCHES franges
    (algunes poden quedar buides) excepte si totes les mitjanes són iguals."""
    ratings = [r for _res, r in games]
    lo, hi = min(ratings), max(ratings)
    if hi <= lo:
        # Tots els rivals al mateix nivell: una sola franja.
        edges = [lo, lo]
        n = 1
    else:
        n = N_BRANCHES
        width = (hi - lo) / n
        edges = [lo + k * width for k in range(n + 1)]
        edges[-1] = hi  # tanca exactament al màxim

    buckets = [
        {
            "order": k,
            "label": _fmt(edges[k]) if n == 1 else f"{_fmt(edges[k])}-{_fmt(edges[k + 1])}",
            "rating_min": round(edges[k], 4),
            "rating_max": round(edges[k + 1] if n > 1 else edges[k], 4),
            "wins": 0,
            "losses": 0,
            "draws": 0,
        }
        for k in range(n)
    ]
    span = (hi - lo) or 1.0
    for res, r in games:
        # +eps perquè un valor just al límit (per error de coma flotant) caigui a
        # la franja superior, coherent amb la convenció [lo, hi).
        idx = int((r - lo) / span * n + 1e-9)
        if idx >= n:
            idx = n - 1
        if res == 1:
            buckets[idx]["wins"] += 1
        elif res == -1:
            buckets[idx]["losses"] += 1
        else:
            buckets[idx]["draws"] += 1
    return buckets


def _weighted_index(games: list[tuple[int, float]]) -> float | None:
    """% de victòries ponderat pel nivell del rival (només decisives)."""
    num = den = 0.0
    for res, r in games:
        if res == 0:
            continue
        den += r
        if res == 1:
            num += r
    return round(100 * num / den, 1) if den > 0 else None


def _crossover(buckets: list[dict]) -> float | None:
    """Nivell de rival on la taxa de victòries creua el 50%, interpolat sobre els
    punts mitjos de les branques amb partides decisives."""
    pts = []
    for b in buckets:
        dec = b["wins"] + b["losses"]
        if dec:
            mid = (b["rating_min"] + b["rating_max"]) / 2
            pts.append((mid, b["wins"] / dec))
    if not pts:
        return None
    if all(wr >= 0.5 for _m, wr in pts):
        return round(pts[-1][0], 3)  # competitiu fins al rival més fort
    if all(wr < 0.5 for _m, wr in pts):
        return round(pts[0][0], 3)  # per sota de tot el rang
    for (m0, w0), (m1, w1) in pairwise(pts):
        if w0 >= 0.5 > w1:
            if w1 == w0:
                return round(m1, 3)
            return round(m0 + (0.5 - w0) * (m1 - m0) / (w1 - w0), 3)
    return round(pts[-1][0], 3)


def _opp_rating_rows(
    conn: sqlite3.Connection, modalitat_codi: int, player_ids: list[int] | None
) -> list[tuple[int, int, float]]:
    """(player_id, res, opp_rating) per cada partida-subjecte de la modalitat.

    `res` ∈ {1, 0, -1}. `opp_rating` = mitjana de rànquing del rival al moment de
    la partida (link de num_seq mínim) amb fallback a la mitjana de la partida.
    Les partides sense cap mitjana de rival queden excloses."""
    filt, params = "", []
    if player_ids is not None:
        ph = ",".join("?" * len(player_ids))
        filt = f"WHERE me IN ({ph})"
        params = list(player_ids)

    sql = f"""
        WITH tb AS (SELECT id AS mid FROM modalitats WHERE codi_fcb = {int(modalitat_codi)}),
        subj AS (
            SELECT g.id AS game_id, g.player1_id AS me, g.player2_id AS opp,
                   CASE WHEN g.guanyador_id = g.player1_id THEN 1
                        WHEN g.guanyador_id IS NULL THEN 0 ELSE -1 END AS res,
                   g.caramboles2 AS opp_car, g.entrades AS ent
            FROM games g WHERE g.modalitat_id = (SELECT mid FROM tb)
            UNION ALL
            SELECT g.id, g.player2_id, g.player1_id,
                   CASE WHEN g.guanyador_id = g.player2_id THEN 1
                        WHEN g.guanyador_id IS NULL THEN 0 ELSE -1 END,
                   g.caramboles1, g.entrades
            FROM games g WHERE g.modalitat_id = (SELECT mid FROM tb)
        ),
        rated AS (
            SELECT s.me, s.res,
                COALESCE(
                    (SELECT e.mitjana_general
                     FROM ranking_game_links l
                     JOIN rankings r ON r.id = l.ranking_id
                                    AND r.modalitat_id = (SELECT mid FROM tb)
                     JOIN ranking_entries e ON e.ranking_id = r.id
                                           AND e.player_id = l.player_id_origen
                     WHERE l.game_id = s.game_id AND l.player_id_origen = s.opp
                     ORDER BY r.num_seq ASC LIMIT 1),
                    (CAST(s.opp_car AS REAL) / NULLIF(s.ent, 0))
                ) AS opp_rating
            FROM subj s
        )
        SELECT me, res, opp_rating FROM rated {filt}
    """
    out = []
    for me, res, opp_rating in conn.execute(sql, params):
        if opp_rating is not None:
            out.append((me, res, float(opp_rating)))
    return out


def rating_breakdown(
    conn: sqlite3.Connection,
    modalitat_codi: int = 1,
    player_ids: list[int] | None = None,
) -> dict[int, dict]:
    """Perfil de rendiment per nivell de rival, per jugador.

    Retorna `{player_id: {"buckets": [...], "weighted_index": float|None,
    "crossover": float|None, "total": int}}`. Les branques són adaptatives
    (N_BRANCHES franges d'igual amplada sobre el rang de rivals del jugador). De
    moment només Tres bandes; per a altres modalitats retorna {}."""
    if modalitat_codi != 1:
        return {}
    if player_ids is not None and not player_ids:
        return {}

    by_player: dict[int, list[tuple[int, float]]] = {}
    for me, res, rating in _opp_rating_rows(conn, modalitat_codi, player_ids):
        by_player.setdefault(me, []).append((res, rating))

    out: dict[int, dict] = {}
    for pid, games in by_player.items():
        buckets = _adaptive_buckets(games)
        out[pid] = {
            "buckets": buckets,
            "weighted_index": _weighted_index(games),
            "crossover": _crossover(buckets),
            "total": len(games),
        }
    return out
