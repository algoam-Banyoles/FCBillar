-- FCBillar cloud schema — rendiment per nivell d'oponent (aranya de la fitxa).
--
-- Precomputat al desktop (fcbillar.analytics.rating_breakdown) i pujat per
-- cloud_sync.publish_rating_buckets. Una fila per (jugador, modalitat, grup).
-- De moment només Tres bandes (modalitat_codi = 1). RLS: lectura pública.

create table if not exists fcbillar.player_rating_buckets (
    player_fcb_id   text    not null,
    modalitat_codi  integer not null,
    bucket          text    not null,   -- ge1000 | b0800 | b0600 | b0400 | lt0400
    bucket_order    integer,            -- 0 = més fort … 4 = més feble
    label           text,               -- etiqueta llegible (p.ex. '0,800–1,000')
    wins            integer not null default 0,
    losses          integer not null default 0,
    draws           integer not null default 0,
    primary key (player_fcb_id, modalitat_codi, bucket)
);
create index if not exists idx_fcbillar_rating_buckets_player
    on fcbillar.player_rating_buckets(player_fcb_id, modalitat_codi);

alter table fcbillar.player_rating_buckets enable row level security;
drop policy if exists "read player_rating_buckets" on fcbillar.player_rating_buckets;
create policy "read player_rating_buckets" on fcbillar.player_rating_buckets
    for select to anon, authenticated using (true);
