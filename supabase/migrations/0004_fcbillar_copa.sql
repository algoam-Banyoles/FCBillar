-- FCBillar cloud schema — FASE 4: Copa Catalana (classificacions per fase/grup).
--
-- La copa es juga per fases (jornada 1a/2a/3a…), cada fase amb grups petits.
-- Les classificacions ja venen calculades a la BD local (copa_classificacio),
-- així que només es repliquen. RLS de lectura pública.

create table if not exists fcbillar.copa_groups (
    edicio_id    integer not null,
    jornada      integer not null,
    grup_id      integer not null,
    grup_nom     text,
    jornada_nom  text,
    ordre        integer,
    primary key (edicio_id, jornada, grup_id)
);

create table if not exists fcbillar.copa_standings (
    edicio_id integer not null,
    jornada   integer not null,
    grup_id   integer not null,
    posicio   integer,
    equip     text not null,
    punts     integer,
    parcials  integer,
    mitjana   double precision,
    primary key (edicio_id, jornada, grup_id, equip)
);
create index if not exists idx_fcbillar_copa_st_grup
    on fcbillar.copa_standings(edicio_id, jornada, grup_id);

alter table fcbillar.copa_groups    enable row level security;
alter table fcbillar.copa_standings enable row level security;
create policy "read copa_groups"    on fcbillar.copa_groups    for select to anon, authenticated using (true);
create policy "read copa_standings" on fcbillar.copa_standings for select to anon, authenticated using (true);
