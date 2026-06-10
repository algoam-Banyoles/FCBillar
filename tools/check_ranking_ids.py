import sqlite3

conn = sqlite3.connect('data/fcbillar.db')
cur = conn.cursor()

# Get ranking ids
cur.execute("""
SELECT id, num_seq, modalitat_id
FROM rankings
WHERE modalitat_id = 1
ORDER BY num_seq DESC
LIMIT 5
""")
print("=== Rankings per modalitat 1 ===")
for row in cur.fetchall():
    print(row)

# Get player id for fcb_id 843
cur.execute("SELECT id FROM players WHERE fcb_id = ?", ('843',))
player_id = cur.fetchone()[0]

# Check links for num_seq=121
cur.execute("""
SELECT COUNT(*) FROM ranking_game_links rgl
JOIN rankings r ON r.id = rgl.ranking_id
WHERE r.num_seq = 121 AND r.modalitat_id = 1 AND rgl.player_id_origen = ?
""", (player_id,))
print(f"\nLinks for num_seq=121 modalitat 1: {cur.fetchone()[0]}")

# Check links for num_seq=122
cur.execute("""
SELECT COUNT(*) FROM ranking_game_links rgl
JOIN rankings r ON r.id = rgl.ranking_id
WHERE r.num_seq = 122 AND r.modalitat_id = 1 AND rgl.player_id_origen = ?
""", (player_id,))
print(f"Links for num_seq=122 modalitat 1: {cur.fetchone()[0]}")

conn.close()
