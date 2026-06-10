import sqlite3

dbs = ['data/fcbillar.db', 'data/fcbillar.db.bak-presync']
player = '843'
for db in dbs:
    try:
        conn = sqlite3.connect(db)
        cur = conn.cursor()
        cur.execute("select count(*) from ranking_game_links rgl join players p on p.id=rgl.player_id_origen where p.fcb_id=?", (player,))
        cnt = cur.fetchone()[0]
        print(db, cnt)
    except Exception as e:
        print(db, 'ERROR', e)
    finally:
        try:
            conn.close()
        except:
            pass
