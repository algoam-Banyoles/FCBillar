import sqlite3
import sys
from pprint import pprint


def compare(db_path: str, player_fcb_id: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    row = conn.execute("SELECT id, nom FROM players WHERE fcb_id = ?", (player_fcb_id,)).fetchone()
    if not row:
        print(f"Player {player_fcb_id} not found in {db_path}")
        return
    pid = row["id"]
    print(f"Player {player_fcb_id} -> id={pid}, nom={row['nom']}")

    # find modalitats where this player has ranking_entries
    mods = conn.execute(
        "SELECT DISTINCT m.codi_fcb FROM ranking_entries re JOIN rankings r ON r.id=re.ranking_id JOIN modalitats m ON m.id=r.modalitat_id WHERE re.player_id = ?",
        (pid,),
    ).fetchall()
    if not mods:
        print("No ranking entries for player")
        return

    for m in mods:
        codi = m["codi_fcb"]
        print('\n=== Modalitat', codi, '===')

        # latest ranking id for this modalitat
        latest = conn.execute(
            "SELECT id, num_seq FROM rankings WHERE modalitat_id = (SELECT id FROM modalitats WHERE codi_fcb=?) ORDER BY num_seq DESC LIMIT 1",
            (codi,),
        ).fetchone()
        if not latest:
            print(' no rankings found')
            continue
        rid = latest["id"]
        print(' latest num_seq=', latest['num_seq'], 'id=', rid)

        # linked games (current used)
        linked = conn.execute(
            "SELECT g.id, g.data_partida, CASE WHEN g.player1_id = ? THEN g.caramboles1 ELSE g.caramboles2 END AS caramboles, g.entrades FROM ranking_game_links rgl JOIN games g ON g.id = rgl.game_id WHERE rgl.ranking_id = ? AND rgl.player_id_origen = ? ORDER BY g.data_partida",
            (pid, rid, pid),
        ).fetchall()
        lc = len(linked)
        lcar = sum((r['caramboles'] or 0) for r in linked)
        lent = sum((r['entrades'] or 0) for r in linked)
        print(f' linked games: {lc}, caramboles_sum={lcar}, entrades_sum={lent}')

        # reported by ranking entry (extras_json)
        reported = conn.execute(
            "SELECT re.partides, re.mitjana_general, json_extract(re.extras_json, '$.caramboles') AS caramboles, json_extract(re.extras_json, '$.entrades') AS entrades FROM ranking_entries re WHERE re.ranking_id = ? AND re.player_id = ?",
            (rid, pid),
        ).fetchone()
        if reported:
            print(' reported by ranking entry:', dict(reported))
        else:
            print(' no ranking entry for this ranking/player')

        # also list linked game ids
        if linked:
            print(' linked game ids (last 10):')
            for r in linked[-10:]:
                print('  ', r['data_partida'], r['id'], r['caramboles'], r['entrades'])


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('Usage: compare_player.py <db_path> <player_fcb_id>')
        sys.exit(1)
    compare(sys.argv[1], sys.argv[2])
