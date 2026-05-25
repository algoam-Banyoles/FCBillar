"""Orquestració de la ingesta."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from fcbillar.config import Settings, get_settings
from fcbillar.db.migrations import ensure_schema
from fcbillar.db.repository import Repository
from fcbillar.models import Game, Ranking, RankingGameLink
from fcbillar.scraper.client import ScraperClient
from fcbillar.scraper.parsers import (
    HistorialEntry,
    HomeRankingsResult,
    RawGameRow,
    parse_home_current_rankings,
    parse_partides_jugador,
    parse_ranking,
    parse_ranking_historial,
)
from fcbillar.scraper.url_builder import all_ranking_url_candidates

log = logging.getLogger(__name__)


@dataclass
class FetchResult:
    url: str
    fmt: str
    html: str


@dataclass
class IngestRankingResult:
    fetch: FetchResult
    players_upserted: int
    entries_upserted: int


def fetch_ranking_html(
    client: ScraperClient,
    num_seq: int,
    modalitat_codi_fcb: int,
    *,
    preferred_format: str | None = None,
) -> FetchResult | None:
    """Prova els formats d'URL i retorna el primer que retorni rànquing parsejable.

    Amb `preferred_format` (p.ex. 'data' o 'datahome'), prova aquest primer
    i l'altre com a fallback. Sense, l'ordre per defecte de
    `all_ranking_url_candidates` és 'datahome' primer (rànquing actual).
    """
    settings = client.settings
    candidates = all_ranking_url_candidates(settings.base_url, num_seq, modalitat_codi_fcb)
    if preferred_format is not None:
        candidates = sorted(
            candidates, key=lambda c: 0 if c[0] == preferred_format else 1
        )
    for fmt, url in candidates:
        try:
            html = client.fetch_html(url)
        except Exception as e:
            log.warning("Fallat fetch %s: %s", url, e)
            continue
        if _looks_like_valid_ranking(html):
            return FetchResult(url=url, fmt=fmt, html=html)
        log.info("URL %s retorna HTML però no sembla rànquing vàlid", url)
    return None


def _looks_like_valid_ranking(html: str) -> bool:
    """Heurística estricta: rànquing vàlid té la secció principal + una taula.

    El portal sovint serveix una pàgina d'error 'silenciosa' (200 OK, HTML
    petit) quan demanes un num_seq amb el format equivocat (p.ex. 'datahome'
    per a un rànquing antic). Aquesta heurística evita acceptar-la.
    """
    if not html or len(html) < 500:
        return False
    if "formloguinacion" in html:
        return False
    # La secció + taula són el marcador estructural del rànquing.
    if "three fourths padded" not in html or "<table" not in html:
        return False
    return True


def ingest_ranking(
    client: ScraperClient,
    num_seq: int,
    modalitat_codi_fcb: int,
    *,
    settings: Settings | None = None,
    preferred_format: str | None = None,
) -> IngestRankingResult | None:
    """Descarrega un rànquing, el parseja i el persisteix a la BD."""
    settings = settings or client.settings
    fetched = fetch_ranking_html(
        client, num_seq, modalitat_codi_fcb, preferred_format=preferred_format
    )
    if fetched is None:
        return None

    parsed = parse_ranking(fetched.html, num_seq, modalitat_codi_fcb)

    conn = ensure_schema(settings.db_path)
    repo = Repository(conn)
    ranking_id = repo.upsert_ranking(
        Ranking(
            num_seq=num_seq,
            modalitat_codi_fcb=modalitat_codi_fcb,
            url=fetched.url,
            format_url=fetched.fmt,
        )
    )
    # Upsert primer tots els jugadors perquè les entries els referencien.
    for player in parsed.players:
        repo.upsert_player(player)
    for entry in parsed.entries:
        repo.upsert_ranking_entry(ranking_id, entry)

    log.info(
        "Ingerit rànquing %s/%s: %d jugadors, %d entries",
        num_seq,
        modalitat_codi_fcb,
        len(parsed.players),
        len(parsed.entries),
    )
    return IngestRankingResult(
        fetch=fetched,
        players_upserted=len(parsed.players),
        entries_upserted=len(parsed.entries),
    )


@dataclass
class IngestPartidesResult:
    games_upserted: int
    games_skipped_missing_opponent: int
    links_created: int


# Mapeig de format del rànquing → segment de la URL de partides per jugador.
# Mateix patró que rànquings: 'datahome' (actual) usa 'partideshome', 'data'
# (històric) usa 'partides'.
_PARTIDES_SEGMENT_BY_FORMAT = {
    "datahome": "partideshome",
    "data": "partides",
}


def _partides_url(
    base_url: str,
    num_seq: int,
    modalitat: int,
    player_fcb_id: str,
    format_url: str = "datahome",
) -> str:
    segment = _PARTIDES_SEGMENT_BY_FORMAT.get(format_url, "partideshome")
    return (
        f"{base_url.rstrip('/')}/ca/jugador/ranking/{segment}/"
        f"{num_seq}/{modalitat}/{player_fcb_id}"
    )


def ingest_partides(
    client: ScraperClient,
    num_seq: int,
    modalitat_codi_fcb: int,
    player_fcb_id: str,
    *,
    settings: Settings | None = None,
) -> IngestPartidesResult:
    """Descarrega partideshome d'un jugador en un rànquing i les persisteix.

    El portal exposa noms però no fcb_ids dels contraris. Resolem nom → fcb_id
    contra els players ja existents a la BD (vinguts d'un rànquing previ). Si
    el contrari no existeix, saltem la partida i ho comptabilitzem.

    Requereix que el rànquing (num_seq, modalitat) ja estigui inserit a la BD
    perquè la traçabilitat ranking_game_links pugui referenciar-lo.
    """
    settings = settings or client.settings
    conn = ensure_schema(settings.db_path)
    repo = Repository(conn)

    owner_nom = repo.get_player_nom_by_fcb_id(player_fcb_id)
    if owner_nom is None:
        raise ValueError(
            f"Player {player_fcb_id} no està a la BD; "
            f"ingest primer el rànquing on apareix."
        )
    format_url = repo.get_ranking_format_url(num_seq, modalitat_codi_fcb)
    if format_url is None:
        raise ValueError(
            f"Rànquing {num_seq}/{modalitat_codi_fcb} no està a la BD; "
            f"`ingest-ranking {num_seq} {modalitat_codi_fcb}` primer."
        )

    url = _partides_url(
        settings.base_url, num_seq, modalitat_codi_fcb, player_fcb_id, format_url=format_url
    )
    html = client.fetch_html(url)
    parsed = parse_partides_jugador(html)

    upserted = 0
    skipped = 0
    links = 0
    for row in parsed.rows:
        game = _build_game_from_raw_row(row, modalitat_codi_fcb, owner_nom, repo)
        if game is None:
            skipped += 1
            continue
        repo.upsert_game(game)
        upserted += 1
        repo.link_game_to_ranking(
            RankingGameLink(
                ranking_num_seq=num_seq,
                ranking_modalitat=modalitat_codi_fcb,
                game_id=game.id_natural,
                player_fcb_id_origen=player_fcb_id,
            )
        )
        links += 1

    log.info(
        "Partides %s/%s/%s: %d desades, %d saltades (contraris no a BD), %d links",
        num_seq,
        modalitat_codi_fcb,
        player_fcb_id,
        upserted,
        skipped,
        links,
    )
    return IngestPartidesResult(
        games_upserted=upserted,
        games_skipped_missing_opponent=skipped,
        links_created=links,
    )


def _build_game_from_raw_row(
    row: RawGameRow,
    modalitat_codi_fcb: int,
    owner_nom: str,
    repo: Repository,
) -> Game | None:
    """Resol noms a fcb_ids i construeix un Game. Retorna None si no es pot."""
    local_fcb = repo.get_player_fcb_id_by_nom(row.local_nom)
    visitant_fcb = repo.get_player_fcb_id_by_nom(row.visitant_nom)
    if local_fcb is None or visitant_fcb is None:
        log.debug(
            "Salto partida %s %s vs %s: local_fcb=%s visitant_fcb=%s",
            row.data_partida,
            row.local_nom,
            row.visitant_nom,
            local_fcb,
            visitant_fcb,
        )
        return None
    # Sanity check: l'owner ha de coincidir amb local o visitant.
    if owner_nom not in (row.local_nom, row.visitant_nom):
        log.warning(
            "Owner %r no apareix com a local/visitant a fila %s: %r vs %r",
            owner_nom,
            row.data_partida,
            row.local_nom,
            row.visitant_nom,
        )
    # Guanyador: el que té més punts (sistema lliga 0/1/2; en individual 0/2).
    guanyador_fcb: str | None = None
    if row.local_punts is not None and row.visitant_punts is not None:
        if row.local_punts > row.visitant_punts:
            guanyador_fcb = local_fcb
        elif row.visitant_punts > row.local_punts:
            guanyador_fcb = visitant_fcb
    return Game(
        data_partida=row.data_partida,
        competicio_nom=row.competicio,
        modalitat_codi_fcb=modalitat_codi_fcb,
        player1_fcb_id=local_fcb,
        player2_fcb_id=visitant_fcb,
        caramboles1=row.local_caramboles,
        caramboles2=row.visitant_caramboles,
        entrades=row.entrades,
        guanyador_fcb_id=guanyador_fcb,
        extras={
            "punts1": row.local_punts,
            "punts2": row.visitant_punts,
        },
    )


@dataclass
class SyncResult:
    discovered: HomeRankingsResult
    ingested: list[tuple[int, int]]  # llista de (num_seq, modalitat) nous ingerits
    skipped_existing: list[tuple[int, int]]


def discover_current_rankings(client: ScraperClient) -> HomeRankingsResult:
    """Descobreix els rànquings actuals consultant /jugador/home."""
    url = f"{client.settings.base_url.rstrip('/')}/jugador/home"
    html = client.fetch_html(url, use_cache=False)
    return parse_home_current_rankings(html)


def discover_historical_rankings(client: ScraperClient) -> list[HistorialEntry]:
    """Descobreix els rànquings històrics consultant /ca/jugador/ranking/historial.

    El portal mostra els ~15 més recents. Per a un backfill realment complet
    caldria iterar per num_seq més enrere consultant URLs directament, però per
    ara l'historial és la font primària.
    """
    url = f"{client.settings.base_url.rstrip('/')}/ca/jugador/ranking/historial"
    html = client.fetch_html(url, use_cache=False)
    return parse_ranking_historial(html)


def sync_current_rankings(
    client: ScraperClient, *, settings: Settings | None = None
) -> SyncResult:
    """Si la home mostra un rànquing nou per a alguna modalitat, l'ingereix."""
    settings = settings or client.settings
    conn = ensure_schema(settings.db_path)
    repo = Repository(conn)
    home = discover_current_rankings(client)
    ingested: list[tuple[int, int]] = []
    skipped: list[tuple[int, int]] = []
    for current in home.rankings:
        latest_db = repo.latest_ranking_num_seq(current.modalitat_codi_fcb) or 0
        if current.num_seq > latest_db:
            result = ingest_ranking(
                client, current.num_seq, current.modalitat_codi_fcb, settings=settings
            )
            if result is not None:
                ingested.append((current.num_seq, current.modalitat_codi_fcb))
        else:
            skipped.append((current.num_seq, current.modalitat_codi_fcb))
    return SyncResult(discovered=home, ingested=ingested, skipped_existing=skipped)


@dataclass
class BackfillResult:
    ranking_ingested: bool
    players_processed: int
    total_games_upserted: int
    total_games_skipped: int


@dataclass
class HistoricalBackfillResult:
    rankings_processed: list[tuple[int, int]]  # llista (num_seq, modalitat)
    rankings_failed: list[tuple[int, int]]
    total_players_processed: int
    total_games_upserted: int
    total_games_skipped: int


def backfill_ranking(
    client: ScraperClient,
    num_seq: int,
    modalitat_codi_fcb: int,
    *,
    top_n: int | None = None,
    only_followed: bool = False,
    settings: Settings | None = None,
    preferred_format: str | None = None,
) -> BackfillResult:
    """Ingest un rànquing concret + partides dels jugadors filtrats.

    Filtres aplicats sobre les entries del rànquing:
      - `top_n`: només els jugadors amb posició ≤ top_n.
      - `only_followed`: només els jugadors marcats com a seguits.
    """
    settings = settings or client.settings
    res = ingest_ranking(
        client, num_seq, modalitat_codi_fcb, settings=settings, preferred_format=preferred_format
    )
    if res is None:
        return BackfillResult(False, 0, 0, 0)

    conn = ensure_schema(settings.db_path)
    candidates: list[tuple[str, int | None]] = []
    rows = conn.execute(
        """
        SELECT p.fcb_id, e.posicio, p.seguiment
        FROM ranking_entries e
        JOIN players p ON p.id = e.player_id
        JOIN rankings r ON r.id = e.ranking_id
        JOIN modalitats m ON m.id = r.modalitat_id
        WHERE r.num_seq = ? AND m.codi_fcb = ?
        ORDER BY e.posicio ASC NULLS LAST
        """,
        (num_seq, modalitat_codi_fcb),
    ).fetchall()
    for fcb_id, posicio, seguiment in rows:
        if only_followed and not seguiment:
            continue
        if top_n is not None and posicio is not None and posicio > top_n:
            continue
        candidates.append((fcb_id, posicio))

    total_up = 0
    total_skip = 0
    for fcb_id, _ in candidates:
        try:
            r = ingest_partides(
                client, num_seq, modalitat_codi_fcb, fcb_id, settings=settings
            )
            total_up += r.games_upserted
            total_skip += r.games_skipped_missing_opponent
        except Exception as e:
            log.warning("Error ingerint partides de %s: %s", fcb_id, e)

    return BackfillResult(
        ranking_ingested=True,
        players_processed=len(candidates),
        total_games_upserted=total_up,
        total_games_skipped=total_skip,
    )


def backfill_modalitat(
    client: ScraperClient,
    modalitat_codi_fcb: int,
    *,
    top_n: int | None = None,
    only_followed: bool = False,
    settings: Settings | None = None,
) -> BackfillResult:
    """Backfill del rànquing actual d'una modalitat (descobert de /jugador/home)."""
    settings = settings or client.settings
    home = discover_current_rankings(client)
    current = next(
        (r for r in home.rankings if r.modalitat_codi_fcb == modalitat_codi_fcb), None
    )
    if current is None:
        raise ValueError(
            f"Modalitat {modalitat_codi_fcb} no apareix als rànquings actuals de la home"
        )
    return backfill_ranking(
        client,
        current.num_seq,
        modalitat_codi_fcb,
        top_n=top_n,
        only_followed=only_followed,
        settings=settings,
    )


def backfill_historical(
    client: ScraperClient,
    *,
    modalitat_codi_fcb: int | None = None,
    top_n: int | None = None,
    only_followed: bool = False,
    settings: Settings | None = None,
) -> HistoricalBackfillResult:
    """Backfill tots els rànquings que apareixen a l'historial.

    Si es passa `modalitat_codi_fcb`, només es processa aquesta modalitat.
    Iterem en ordre cronològic ascendent (rànquings antics primer) perquè
    els upserts mantinguin coherència temporal.
    """
    settings = settings or client.settings
    entries = discover_historical_rankings(client)
    # Aplanem a llista (num_seq, modalitat) ordenada cronològicament ascendent.
    flat: list[tuple[int, int]] = []
    flat_with_fmt: list[tuple[int, int, str]] = []
    for entry in sorted(entries, key=lambda e: e.data):
        for modalitat, (fmt, num_seq) in entry.rankings.items():
            if modalitat_codi_fcb is not None and modalitat != modalitat_codi_fcb:
                continue
            flat_with_fmt.append((num_seq, modalitat, fmt))

    processed: list[tuple[int, int]] = []
    failed: list[tuple[int, int]] = []
    total_players = 0
    total_up = 0
    total_skip = 0
    for num_seq, modalitat, fmt in flat_with_fmt:
        try:
            res = backfill_ranking(
                client,
                num_seq,
                modalitat,
                top_n=top_n,
                only_followed=only_followed,
                settings=settings,
                preferred_format=fmt,
            )
        except Exception as e:
            log.warning("Backfill històric: error a %s/%s: %s", num_seq, modalitat, e)
            failed.append((num_seq, modalitat))
            continue
        if not res.ranking_ingested:
            failed.append((num_seq, modalitat))
            continue
        processed.append((num_seq, modalitat))
        total_players += res.players_processed
        total_up += res.total_games_upserted
        total_skip += res.total_games_skipped

    return HistoricalBackfillResult(
        rankings_processed=processed,
        rankings_failed=failed,
        total_players_processed=total_players,
        total_games_upserted=total_up,
        total_games_skipped=total_skip,
    )


def set_follow(fcb_id: str, follow: bool, *, settings: Settings | None = None) -> bool:
    """Marca/desmarca un jugador com a seguit. Retorna True si existeix."""
    settings = settings or get_settings()
    conn = ensure_schema(settings.db_path)
    repo = Repository(conn)
    return repo.set_seguiment(fcb_id, follow)


def run_status(settings: Settings | None = None) -> dict[str, int]:
    settings = settings or get_settings()
    conn = ensure_schema(settings.db_path)
    repo = Repository(conn)
    return repo.counts()
