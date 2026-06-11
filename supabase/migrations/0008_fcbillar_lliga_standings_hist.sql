-- FCBillar cloud schema — Classificacions HISTÒRIQUES de lliga (per temporada).
--
-- A diferència de `lliga_standings` (temporada actual, calculada des dels
-- encontres), aquesta taula conté les classificacions REALS scrapejades de
-- l'Historial del portal, per a TOTES les temporades i TOTES les fases, amb el
-- NOM REAL del grup ("FINAL 1a DIVISIÓ", "GRUP A", "PROMOCIÓ-1"…). Així l'app
-- germana pot distingir la fase FINAL de les fases de grup i mostrar el podi
-- real (1r/2n/3r) de cada divisió i temporada.
--
-- Origen: scripts/import_lliga_standings.py → SQLite lliga_standings_hist →
-- publish_lliga_standings_hist (cloud_sync.py). RLS de lectura pública (anon),
-- igual que lliga_standings / open_classifications.

create table if not exists fcbillar.lliga_standings_hist (
    temporada text not null,   -- "2024-2025"
    lliga     text not null,   -- "LLIGA CATALANA TRES BANDES"
    divisio   text not null,   -- "1a DIVISIÓ", "HONOR"…
    grup      text not null,   -- "FINAL 1a DIVISIÓ", "GRUP A", "PROMOCIÓ-1"…
    posicio   integer,         -- posició final dins el grup (1 = campió)
    equip     text not null,   -- "C.B. BANYOLES \"A\""
    pm        integer,         -- punts de match
    pp        integer,         -- punts parcials
    primary key (temporada, lliga, divisio, grup, equip)
);
create index if not exists idx_fcbillar_standings_hist_grup
    on fcbillar.lliga_standings_hist (temporada, lliga, divisio, grup);
create index if not exists idx_fcbillar_standings_hist_equip
    on fcbillar.lliga_standings_hist (equip);

alter table fcbillar.lliga_standings_hist enable row level security;
create policy "read lliga_standings_hist"
    on fcbillar.lliga_standings_hist for select to anon, authenticated using (true);

-- Vista de conveniència: només els podis (1r/2n/3r) de les fases FINAL.
-- security_invoker = respecta la RLS de la taula base (lectura pública).
create or replace view fcbillar.lliga_final_podis
    with (security_invoker = true) as
    select temporada, lliga, divisio, grup, posicio, equip, pm, pp
    from fcbillar.lliga_standings_hist
    where grup ilike 'FINAL%' and posicio <= 3
    order by temporada desc, lliga, divisio, posicio;

grant select on fcbillar.lliga_final_podis to anon, authenticated;
