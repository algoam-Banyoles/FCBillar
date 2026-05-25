# FCBillar

Scraper i base de dades local per fer seguiment dels jugadors del club i d'altres jugadors d'interès en els campionats de caràmbola de la **Federació Catalana de Billar** (https://www.fcbillar.cat/).

## Què fa

- Es connecta a la intranet de jugador amb les teves credencials federatives.
- Descobreix els rànquings mensuals per modalitat (lliure, banda, tres bandes, quadre, etc.).
- Descarrega les partides que conformen cada rànquing per a cada jugador i les dedupliquica (les partides apareixen a tots dos jugadors i en més d'un rànquing per la finestra lliscant de 10-15 partides).
- Backfill històric: recorre tot l'`/jugador/ranking/historial` (els ~15 rànquings més recents) per modalitat.
- **Lliga catalana**: ingest des de les pàgines públiques de lliga (no requereix sessió) per obtenir el **club + equip** de cada jugador per partida, més camps rics no presents a la intranet (sèrie major, àrbitre, assistència).
- Persisteix-ho tot en una BD SQLite local per consulta amb SQL/Pandas/notebooks.
- Gestiona els dos formats d'URL de rànquings (`data` històric, `datahome` actual).

## Requisits

- Python 3.12+
- uv (gestor de paquets/projecte)
- Credencials d'accés a la intranet de jugador de fcbillar.cat

## Instal·lació

```powershell
uv sync
uv run playwright install chromium
Copy-Item .env.example .env
# edita .env i posa FCB_USER / FCB_PASS
```

## Ús bàsic

```powershell
# Verifica que el login funciona i desa la sessió (resol captcha manualment)
uv run fcbillar login

# Crea/actualitza l'esquema de la BD (seedeja modalitats)
uv run fcbillar init-db

# Sincronitza: detecta i ingest rànquings nous publicats a la home
uv run fcbillar sync

# Ingest del rànquing actual d'una modalitat + partides dels top N jugadors
#   modalitats: 1=Tres bandes, 2=Lliure, 3=Quadre 47/2, 4=Banda, 6=Quadre 71/2
uv run fcbillar backfill 1 --top 20

# Backfill històric: tot l'historial (els ~15 rànquings més recents) d'una modalitat
uv run fcbillar backfill 1 --historical --top 5
# (modalitat=0 amb --historical processa totes les modalitats)

# Mateix però només pels jugadors marcats com a seguits
uv run fcbillar backfill 1 --only-followed

# Marca/desmarca jugadors d'interès (pel seu fcb_id intern del portal)
uv run fcbillar follow 566
uv run fcbillar follow 566 --off

# Ingest puntual d'un rànquing concret
uv run fcbillar ingest-ranking 121 2

# Ingest puntual de les partides d'un jugador en un rànquing
uv run fcbillar ingest-partides 121 2 566

# Ingest d'una jornada de lliga catalana (encontres + partides amb club/equip)
#   <lliga> <divisio> <grup> <jornada> [--modalitat N] [--data YYYY-MM-DD]
#   IMPORTANT: cal haver fet ingest-ranking abans per a la mateixa modalitat
#   (els noms dels jugadors es resolen a fcb_id contra la BD).
uv run fcbillar ingest-lliga-jornada 36 148 316 2593 --modalitat 1 --data 2025-09-27

# Estat de la BD
uv run fcbillar status
```

## Pipeline típic per a una temporada nova

```powershell
# 1. Login si no tens sessió desada
uv run fcbillar login

# 2. Ingest dels rànquings actuals de totes les modalitats (alimenta la BD de jugadors)
uv run fcbillar sync

# 3. Ingest dels rànquings històrics (15 més recents al portal)
uv run fcbillar backfill 0 --historical

# 4. Per a cada jornada de lliga que vulguis ingerir (manualment de moment):
uv run fcbillar ingest-lliga-jornada 36 148 316 2593 --modalitat 1 --data 2025-09-27
# ... una crida per jornada
```

## Identificadors

El portal exposa només un **ID intern numèric** per jugador (`fcb_id`, ex. "566"),
no el codi federatiu real. És aquest id el que apareix a les URLs `partideshome/.../.../{id}`.
Si en algun moment volem el codi federatiu real, s'haurà d'extreure del perfil
individual i afegir com a columna addicional.

Per a **clubs** el portal no exposa cap id intern. Fem servir el nom del club tal
com surt al text de l'equip a les pàgines de lliga ("C.B. SANTS") com a `fcb_id`
del club. La pàgina pública `/clubs/5/Federacio` fa servir noms lleugerament
diferents ("C.B.SANTS" sense espai); unificació fuzzy queda pendent.

## Semàntica del rànquing

Important: el rànquing mensual del portal mostra a cada jugador les **N partides
més recents puntuables** (p.ex. les 20 més recents del lliure), no totes les
partides d'una finestra temporal fixa. Conseqüència: per a cobertura temporal
real, NO fer servir `--top 1` (acumula forats si el líder està inactiu); fer
servir backfill sense `--top` per ingerir tots els jugadors del rànquing.

## Estructura

```text
src/fcbillar/
├── config.py         # Settings (Pydantic)
├── auth.py           # Login intranet (polling estable del form)
├── scraper/
│   ├── client.py     # Playwright + caché + rate limit, networkidle no-fatal
│   ├── url_builder.py # URLs de rànquing (formats 'data' / 'datahome')
│   └── parsers.py    # parse_ranking, parse_partides_jugador, parse_home,
│                     # parse_historial, parse_lliga_* (grups/jornades/encontres/partides)
├── db/
│   ├── schema.sql    # Schema v2: rànquings + lliga (clubs/equips/encontres/temporades)
│   ├── migrations.py # SCHEMA_VERSION + _migrate_v1_to_v2
│   └── repository.py # Upserts idempotents, dedup, FK enforced
├── models.py         # Dataclasses (Player, Game amb id_natural per dedup,
│                     # Club, Equip, Temporada, EncontreLliga, ...)
├── pipeline.py       # ingest_ranking, ingest_partides, sync, backfill (+ historical),
│                     # ingest_lliga_encontre, ingest_lliga_jornada
└── cli.py            # CLI Typer
```

## Esquema de la BD (v2)

```text
clubs ─< equips ─< encontres_lliga ─< games
                                       │
players ───────────────────────────────┤
                                       │
modalitats ─< rankings ─< ranking_entries
                                  │
                                  └─< games (via ranking_game_links)

temporades ───< games
              └< encontres_lliga
```

- `games` és deduplicada via `id_natural` (hash determinista de data, modalitat
  i jugadors ordenats). Una partida ingerida primer via partideshome (sense club)
  i després via lliga (amb club/àrbitre) es complementa naturalment per
  COALESCE a `upsert_game`.
- `ranking_game_links` és la traçabilitat: en quin rànquing va aparèixer una
  partida i vista des de quin jugador.

## Notes

Projecte per a ús personal de l'usuari (federat). No el feu servir per a recol·lecció massiva de dades ni distribuir-les sense permís de la federació.
