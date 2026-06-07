-- FCBillar cloud schema — FASE 2: partides (per a la fitxa de jugador).
--
-- Denormalitzada (noms de jugador inclosos) i sense FK perquè el sync sigui
-- senzill i la lectura no necessiti joins. RLS: lectura pública.

create table if not exists fcbillar.games (
    id               text primary key,   -- id natural (hash) de la BD SQLite
    data_partida     date,
    modalitat_codi   integer,
    competicio       text,                -- LLIGA | COPA | INDIVIDUAL
    player1_fcb_id   text,
    player1_nom      text,
    caramboles1      integer,
    serie_max1       integer,
    player2_fcb_id   text,
    player2_nom      text,
    caramboles2      integer,
    serie_max2       integer,
    entrades         integer,
    guanyador_fcb_id text
);
create index if not exists idx_fcbillar_games_p1 on fcbillar.games(player1_fcb_id);
create index if not exists idx_fcbillar_games_p2 on fcbillar.games(player2_fcb_id);
create index if not exists idx_fcbillar_games_data on fcbillar.games(data_partida desc);

alter table fcbillar.games enable row level security;
create policy "read games" on fcbillar.games for select to anon, authenticated using (true);
