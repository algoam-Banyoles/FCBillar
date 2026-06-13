-- FCBillar cloud schema — indicadors de l'aranya de rendiment per jugador.
--
-- Complementa fcbillar.player_rating_buckets (ara amb branques adaptatives,
-- claus b0..b5 i etiquetes de rang per jugador). Aquí desem els dos indicadors
-- calculats a fcbillar.analytics: índex de rendiment ponderat pel nivell del
-- rival i el nivell de creuament del 50% de victòries. Una fila per
-- (jugador, modalitat). De moment només Tres bandes. RLS: lectura pública.

create table if not exists fcbillar.player_rating_index (
    player_fcb_id   text    not null,
    modalitat_codi  integer not null,
    weighted_index  real,               -- % victòries ponderat pel nivell (0-100)
    crossover       real,               -- mitjana de rival on es creua el 50%
    total_games     integer not null default 0,
    primary key (player_fcb_id, modalitat_codi)
);

alter table fcbillar.player_rating_index enable row level security;
drop policy if exists "read player_rating_index" on fcbillar.player_rating_index;
create policy "read player_rating_index" on fcbillar.player_rating_index
    for select to anon, authenticated using (true);
