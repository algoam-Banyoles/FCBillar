import sqlite3

conn = sqlite3.connect('data/fcbillar.db')
cur = conn.cursor()

# Get schema for games table
cur.execute("PRAGMA table_info(games)")
print("=== Games table schema ===")
for row in cur.fetchall():
    print(row)

# Get schema for players table
cur.execute("PRAGMA table_info(players)")
print("\n=== Players table schema ===")
for row in cur.fetchall():
    print(row)

conn.close()
