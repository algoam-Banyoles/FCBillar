import sqlite3

conn = sqlite3.connect('data/fcbillar.db')
cur = conn.cursor()

# Get player id for fcb_id 843
cur.execute("SELECT id FROM players WHERE fcb_id = ?", ('843',))
player_id = cur.fetchone()[0]

# Delete all links for player 843 for ranking 122/1 (id=244)
cur.execute("""
DELETE FROM ranking_game_links
WHERE ranking_id = 244 AND player_id_origen = ?
""", (player_id,))

print(f"Deleted {cur.rowcount} links for player 843 ranking 122/1")

conn.commit()
conn.close()
