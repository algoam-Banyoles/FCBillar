import sqlite3

conn = sqlite3.connect('data/fcbillar.db')
cur = conn.cursor()

# Get player id for fcb_id 843
cur.execute("SELECT id FROM players WHERE fcb_id = ?", ('843',))
row = cur.fetchone()
if not row:
    print("Player not found")
    conn.close()
    exit(1)
player_id = row[0]
print(f"Player 843 has id={player_id}")

# Veure totes les partides del jugador 843
print("\n=== Totes les partides del jugador (modalitat 1, últimes) ===")
cur.execute("""
SELECT g.id, g.data_partida, g.modalitat_id, p1.fcb_id, p2.fcb_id,
       g.caramboles1, g.caramboles2, g.entrades
FROM games g
JOIN players p1 ON p1.id = g.player1_id
JOIN players p2 ON p2.id = g.player2_id
WHERE (g.player1_id = ? OR g.player2_id = ?) AND g.modalitat_id = 1
ORDER BY g.data_partida DESC
LIMIT 20
""", (player_id, player_id))
for row in cur.fetchall():
    print(row)

# Veure comptatge per modalitat
print("\n=== Comptatge per modalitat ===")
cur.execute("""
SELECT g.modalitat_id, COUNT(*)
FROM games g
WHERE g.player1_id = ? OR g.player2_id = ?
GROUP BY g.modalitat_id
ORDER BY g.modalitat_id
""", (player_id, player_id))
for row in cur.fetchall():
    print(row)

# Veure els links creats per a ranking 121/1 (id=1)
print("\n=== Links per a ranking 121/1 (id=1) ===")
cur.execute("""
SELECT COUNT(*)
FROM ranking_game_links rgl
WHERE rgl.ranking_id = 1 AND rgl.player_id_origen = ?
""", (player_id,))
print("Total links:", cur.fetchone()[0])

cur.execute("""
SELECT rgl.game_id, g.data_partida, g.caramboles1, g.caramboles2, g.entrades,
       p1.fcb_id, p2.fcb_id
FROM ranking_game_links rgl
JOIN games g ON g.id = rgl.game_id
JOIN players p1 ON p1.id = g.player1_id
JOIN players p2 ON p2.id = g.player2_id
WHERE rgl.ranking_id = 1 AND rgl.player_id_origen = ?
ORDER BY g.data_partida DESC
""", (player_id,))
print("Linked games:")
for row in cur.fetchall():
    print(row)

conn.close()
