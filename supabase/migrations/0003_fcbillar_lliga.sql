-- FCBillar cloud schema — FASE 3: classificacions de lliga.
--
-- lliga_groups: grups presents (divisió HONOR/1a/…, grup A/B/FINAL) amb noms.
-- lliga_standings: classificació per grup (calculada des dels encontres:
--   punts = 3·G + 1·E; ordre per punts i diferència de parcials).
-- Denormalitzat (nom d'equip resolt) i RLS de lectura pública.

create table if not exists fcbillar.lliga_groups (
    lliga_id     integer not null,
    divisio_id   integer not null,
    grup_id      integer not null,
    divisio_nom  text,
    grup_nom     text,
    primary key (lliga_id, divisio_id, grup_id)
);

create table if not exists fcbillar.lliga_standings (
    lliga_id    integer not null,
    divisio_id  integer not null,
    grup_id     integer not null,
    posicio     integer,
    equip       text not null,
    club_fcb_id text,
    pj integer, g integer, e integer, p integer,
    punts integer,
    pf integer, pc integer,
    primary key (lliga_id, divisio_id, grup_id, equip)
);
create index if not exists idx_fcbillar_standings_grup
    on fcbillar.lliga_standings(lliga_id, divisio_id, grup_id);

alter table fcbillar.lliga_groups    enable row level security;
alter table fcbillar.lliga_standings enable row level security;
create policy "read lliga_groups"    on fcbillar.lliga_groups    for select to anon, authenticated using (true);
create policy "read lliga_standings" on fcbillar.lliga_standings for select to anon, authenticated using (true);
