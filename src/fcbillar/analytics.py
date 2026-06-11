"""Anàlisi derivada: rendiment d'un jugador per nivell de l'oponent.

Per a la fitxa de jugador volem un gràfic "aranya" amb victòries i derrotes
contra oponents agrupats pel seu **nivell de rànquing en el moment de disputar
la partida**.

Definició de la "mitjana de rànquing de l'oponent en aquell moment" (per cada
partida + oponent O):

1. **Primari** — la `mitjana_general` d'O al snapshot on la partida entra a la
   finestra de rànquing: la fila de `ranking_game_links` d'O per aquesta partida
   amb el `num_seq` mínim (el primer rànquing que la inclou ≈ el moment de la
   partida). És la mateixa relació que fa servir `DataSource.player_games`.
2. **Fallback** — si O no té cap link per aquesta partida, la mitjana de la
   pròpia partida (`caramboles_oponent / entrades`).
3. Si no hi ha cap de les dues (entrades = 0 i sense link) → bucket `sense`
   (s'exclou dels resultats).

De moment només Tres bandes (codi_fcb = 1): les altres modalitats tenen rangs de
mitjana molt diferents i necessiten graelles pròpies. La funció ja rep
`modalitat_codi` per facilitar-ho en el futur.
"""

from __future__ import annotations

import sqlite3

# Grups de Tres bandes: (key, label, lo, hi). `lo` inclusiu, `hi` exclusiu;
# None = infinit. Ordenats del més fort al més feble (= ordre dels eixos del radar).
RATING_BUCKETS_TB: list[tuple[str, str, float | None, float | None]] = [
    ("ge1000", "≥ 1,000", 1.0, None),
    ("b0800", "0,800-1,000", 0.8, 1.0),
    ("b0600", "0,600-0,800", 0.6, 0.8),
    ("b0400", "0,400-0,600", 0.4, 0.6),
    ("lt0400", "< 0,400", None, 0.4),
]


def _bucket_case_sql(col: str = "opp_rating") -> str:
    """Construeix el CASE SQL a partir de RATING_BUCKETS_TB (una sola font de veritat)."""
    whens = [
        f"WHEN {col} >= {lo} THEN '{key}'"
        for key, _label, lo, _hi in RATING_BUCKETS_TB
        if lo is not None
    ]
    # L'últim grup (lo = None) recull la resta de valors no nuls.
    whens.append(f"WHEN {col} IS NOT NULL THEN '{RATING_BUCKETS_TB[-1][0]}'")
    return "CASE " + " ".join(whens) + " ELSE 'sense' END"


def rating_breakdown(
    conn: sqlite3.Connection,
    modalitat_codi: int = 1,
    player_ids: list[int] | None = None,
) -> dict[int, dict[str, dict[str, int]]]:
    """Victòries/derrotes/empats per grup d'oponent, per jugador.

    Retorna `{player_id: {bucket_key: {"wins", "losses", "draws"}}}`. Cada
    partida hi contribueix dues vegades (una per cada jugador com a subjecte).
    Si `player_ids` ve donat, només es calcula per a aquests jugadors (el
    predicat sobre `me` es propaga dins de les CTE, així que és ràpid). De
    moment només per a Tres bandes; per a altres modalitats retorna {}.
    """
    if modalitat_codi != 1:
        return {}
    if player_ids is not None and not player_ids:
        return {}

    case = _bucket_case_sql()
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
        SELECT me AS player_id, {case} AS bucket,
               SUM(CASE WHEN res = 1 THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN res = -1 THEN 1 ELSE 0 END) AS losses,
               SUM(CASE WHEN res = 0 THEN 1 ELSE 0 END) AS draws
        FROM rated
        {filt}
        GROUP BY me, bucket
    """

    out: dict[int, dict[str, dict[str, int]]] = {}
    for r in conn.execute(sql, params):
        bucket = r[1]
        if bucket == "sense":
            continue
        out.setdefault(r[0], {})[bucket] = {
            "wins": r[2] or 0,
            "losses": r[3] or 0,
            "draws": r[4] or 0,
        }
    return out


def rating_breakdown_rows(
    player_buckets: dict[str, dict[str, int]] | None,
) -> list[dict]:
    """Aplana el dict d'un jugador a una llista ordenada amb els 5 grups (zeros inclosos)."""
    player_buckets = player_buckets or {}
    rows = []
    for order, (key, label, _lo, _hi) in enumerate(RATING_BUCKETS_TB):
        b = player_buckets.get(key) or {}
        rows.append({
            "bucket": key,
            "bucket_order": order,
            "label": label,
            "wins": b.get("wins", 0),
            "losses": b.get("losses", 0),
            "draws": b.get("draws", 0),
        })
    return rows
