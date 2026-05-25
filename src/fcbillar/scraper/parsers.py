"""Parsers HTML per a les pàgines de l'intranet de fcbillar.cat."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date

from bs4 import BeautifulSoup, Tag

from fcbillar.models import Player, RankingEntry

log = logging.getLogger(__name__)


# Format de l'href del link "Partides" dins de cada fila del rànquing:
#   ca/jugador/ranking/partideshome/{num_seq}/{modalitat}/{player_fcb_id}  (rànquings actuals)
#   ca/jugador/ranking/partides/{num_seq}/{modalitat}/{player_fcb_id}      (rànquings històrics)
_PARTIDES_HREF_RE = re.compile(
    r"ranking/partides(?:home)?/(\d+)/(\d+)/(\d+)"
)

# Format de l'href dels links de modalitat a l'historial:
#   ca/jugador/ranking/(data|datahome)/{num_seq}/{modalitat}
_HISTORIAL_HREF_RE = re.compile(
    r"ranking/(data|datahome)/(\d+)/(\d+)"
)


def _text(tag: Tag | None) -> str:
    return tag.get_text(strip=True) if tag is not None else ""


def _parse_float(s: str) -> float | None:
    s = s.strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _parse_int(s: str) -> int | None:
    s = s.strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _parse_punts(cell: str) -> tuple[int | None, int | None]:
    """Cel·la 'P / PT' té el format '16 / 20'."""
    parts = [p.strip() for p in cell.split("/")]
    if len(parts) != 2:
        return None, None
    return _parse_int(parts[0]), _parse_int(parts[1])


@dataclass
class RankingParseResult:
    """Resultat de parsejar una pàgina de rànquing."""

    num_seq: int
    modalitat_codi_fcb: int
    players: list[Player]
    entries: list[RankingEntry]


def parse_ranking(html: str, num_seq: int, modalitat_codi_fcb: int) -> RankingParseResult:
    """Parseja una pàgina de rànquing i retorna jugadors + entries.

    La pàgina té una taula amb columnes:
        Ranking | Jugador | MJ | MR | Rang | C | E | P / PT | Def | [Partides]

    El link "Partides" de cada fila conté el fcb_id del jugador. Si no podem
    extreure l'id, saltem la fila (només pot venir de canvis de format que
    no controlem encara).
    """
    soup = BeautifulSoup(html, "lxml")

    # La taula del rànquing viu dins de <section class="three fourths padded">.
    section = soup.select_one("section.three.fourths.padded")
    if section is None:
        raise ValueError("No s'ha trobat la secció principal del rànquing")
    table = section.find("table")
    if table is None:
        raise ValueError("No s'ha trobat la taula del rànquing dins la secció")

    players: list[Player] = []
    entries: list[RankingEntry] = []
    seen_player_ids: set[str] = set()

    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        # La primera fila és <th> (capçalera); files de dades tenen 10 <td>
        if len(cells) < 9:
            continue
        try:
            entry, player = _parse_ranking_row(cells, num_seq, modalitat_codi_fcb)
        except _SkipRow as e:
            log.debug("Salto fila: %s", e)
            continue
        if player.fcb_id not in seen_player_ids:
            players.append(player)
            seen_player_ids.add(player.fcb_id)
        entries.append(entry)

    return RankingParseResult(
        num_seq=num_seq,
        modalitat_codi_fcb=modalitat_codi_fcb,
        players=players,
        entries=entries,
    )


class _SkipRow(Exception):
    """Fila que no podem parsejar — la saltem en silenci."""


def _parse_ranking_row(
    cells: list[Tag], num_seq: int, modalitat_codi_fcb: int
) -> tuple[RankingEntry, Player]:
    # cells: [Ranking, Jugador, MJ, MR, Rang, C, E, P/PT, Def, <Partides>]
    posicio = _parse_int(_text(cells[0]))
    nom = _text(cells[1])
    mj = _parse_float(_text(cells[2]))
    mr = _parse_float(_text(cells[3]))
    rang = _parse_float(_text(cells[4]))
    caramboles = _parse_int(_text(cells[5]))
    entrades = _parse_int(_text(cells[6]))
    punts, punts_totals = _parse_punts(_text(cells[7]))
    definitiva = _text(cells[8]).strip().lower() == "si"

    # L'última cel·la conté el link "Partides" amb l'id del jugador.
    fcb_id = _extract_player_fcb_id(cells[-1])
    if fcb_id is None:
        raise _SkipRow(f"fila sense link de partides parsejable (posicio={posicio}, nom={nom!r})")

    player = Player(fcb_id=fcb_id, nom=nom)
    # MJ = mitjana del jugador; MR = mitjana dels contraris (a extras).
    # El nombre de partides no es publica al rànquing — surt a partideshome.
    entry = RankingEntry(
        ranking_num_seq=num_seq,
        ranking_modalitat=modalitat_codi_fcb,
        player_fcb_id=fcb_id,
        posicio=posicio,
        mitjana_general=mj,
        mitjana_particular=None,
        partides=None,
        extras={
            "mitjana_contraris": mr,
            "rang": rang,
            "caramboles": caramboles,
            "entrades": entrades,
            "punts": punts,
            "punts_totals": punts_totals,
            "definitiva": definitiva,
        },
    )
    return entry, player


def _extract_player_fcb_id(cell: Tag) -> str | None:
    link = cell.find("a", href=True)
    if link is None:
        return None
    m = _PARTIDES_HREF_RE.search(link["href"])
    if m is None:
        return None
    return m.group(3)  # el tercer grup és el player_fcb_id


# --------------------------- historial ---------------------------


@dataclass(frozen=True)
class HistorialEntry:
    """Una fila de l'historial: una data amb els links a cada modalitat."""

    data: date
    rankings: dict[int, tuple[str, int]]  # modalitat_codi_fcb -> (format_url, num_seq)


def parse_ranking_historial(html: str) -> list[HistorialEntry]:
    """Parseja /ca/jugador/ranking/historial.

    La taula té com a capçalera: Data | Modalitats (colspan=5), i cada fila
    de dades té una primera <td> amb la data ISO i les altres amb un <a> per
    modalitat. La URL conté el format (`data` o `datahome`), el num_seq i el
    codi de modalitat.
    """
    soup = BeautifulSoup(html, "lxml")
    section = soup.select_one("section.three.fourths.padded")
    if section is None:
        raise ValueError("No s'ha trobat la secció principal de l'historial")
    table = section.find("table")
    if table is None:
        raise ValueError("No s'ha trobat la taula d'historial")

    out: list[HistorialEntry] = []
    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        if not cells:
            continue
        data_str = _text(cells[0])
        try:
            data_val = date.fromisoformat(data_str)
        except ValueError:
            continue  # fila no de dades
        rankings: dict[int, tuple[str, int]] = {}
        for cell in cells[1:]:
            link = cell.find("a", href=True)
            if link is None:
                continue
            m = _HISTORIAL_HREF_RE.search(link["href"])
            if m is None:
                continue
            fmt, num_seq, modalitat = m.group(1), int(m.group(2)), int(m.group(3))
            rankings[modalitat] = (fmt, num_seq)
        if rankings:
            out.append(HistorialEntry(data=data_val, rankings=rankings))
    return out


# --------------------------- partides per jugador ---------------------------


@dataclass(frozen=True)
class RawGameRow:
    """Una partida tal com surt a /jugador/ranking/partideshome/...

    El portal només dona noms; no exposa el fcb_id del contrincant. El pipeline
    és qui resol nom → fcb_id consultant la BD.
    """

    data_partida: date
    competicio: str  # 'LLIGA', 'INDIVIDUAL', 'COPA', ...
    local_nom: str
    local_punts: int | None
    local_caramboles: int | None
    visitant_nom: str
    visitant_punts: int | None
    visitant_caramboles: int | None
    entrades: int | None


@dataclass
class PartidesParseResult:
    rows: list[RawGameRow] = field(default_factory=list)
    # noms únics que apareixen a les files (per facilitar resolució a la BD)
    noms: set[str] = field(default_factory=set)


def parse_partides_jugador(html: str) -> PartidesParseResult:
    """Parseja /ca/jugador/ranking/partideshome/{num}/{mod}/{player}.

    Les files de la taula es divideixen per separadors `<tr><td colspan=8>`
    amb el nom de la categoria (LLIGA/INDIVIDUAL/COPA). Cada bloc següent va
    associat a aquesta categoria fins al pròxim separador.
    """
    soup = BeautifulSoup(html, "lxml")
    section = soup.select_one("section.three.fourths.padded")
    if section is None:
        raise ValueError("No s'ha trobat la secció principal de partides")
    table = section.find("table")
    if table is None:
        raise ValueError("No s'ha trobat la taula de partides")

    result = PartidesParseResult()
    current_competicio: str | None = None
    for tr in table.find_all("tr"):
        # Capçalera <th>: saltar.
        if tr.find("th") is not None:
            continue
        cells = tr.find_all("td")
        if not cells:
            continue
        # Separador de categoria: única cel·la amb colspan.
        if len(cells) == 1 and cells[0].get("colspan"):
            current_competicio = _text(cells[0]).upper() or None
            continue
        # Files de dades: 8 cel·les.
        if len(cells) < 8 or current_competicio is None:
            continue
        try:
            row = _parse_partida_row(cells, current_competicio)
        except _SkipRow as e:
            log.debug("Salto fila de partides: %s", e)
            continue
        result.rows.append(row)
        result.noms.add(row.local_nom)
        result.noms.add(row.visitant_nom)
    return result


# --------------------------- home del jugador ---------------------------


_HOME_DATA_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


@dataclass(frozen=True)
class CurrentRankingInfo:
    modalitat_codi_fcb: int
    num_seq: int
    format_url: str  # 'data' o 'datahome'


@dataclass(frozen=True)
class HomeRankingsResult:
    data_ranking: date | None  # data del darrer rànquing calculat
    rankings: list[CurrentRankingInfo]


def parse_home_current_rankings(html: str) -> HomeRankingsResult:
    """Extreu els rànquings actuals dels boxes de la home del jugador."""
    soup = BeautifulSoup(html, "lxml")
    # Data del rànquing: dins d'un <h2>Últim ranking calculat ( YYYY-MM-DD )</h2>
    data_ranking: date | None = None
    for h2 in soup.find_all("h2"):
        m = _HOME_DATA_RE.search(h2.get_text())
        if m:
            try:
                data_ranking = date.fromisoformat(m.group(1))
                break
            except ValueError:
                continue

    out: list[CurrentRankingInfo] = []
    for link in soup.select("div.box.success a[href]"):
        m = _HISTORIAL_HREF_RE.search(link["href"])
        if m is None:
            continue
        fmt, num_seq, modalitat = m.group(1), int(m.group(2)), int(m.group(3))
        out.append(
            CurrentRankingInfo(
                modalitat_codi_fcb=modalitat, num_seq=num_seq, format_url=fmt
            )
        )
    return HomeRankingsResult(data_ranking=data_ranking, rankings=out)


# --------------------------- pàgines públiques de lliga ---------------------------


# Regex que matcha URLs de jornades/classificació de lliga:
#   ca/lligues/jornades/{lliga}/{divisio}/{grup}
#   ca/lligues/classificacio/{lliga}/{divisio}/{grup}
_LLIGA_GRUP_HREF_RE = re.compile(
    r"lligues/(?:jornades|classificacio)/(\d+)/(\d+)/(\d+)"
)

# Regex per als encontres dins d'una jornada:
#   ca/lligues/partides/{lliga}/{divisio}/{grup}/{jornada}/{encontre}
_LLIGA_PARTIDES_HREF_RE = re.compile(
    r"lligues/partides/(\d+)/(\d+)/(\d+)/(\d+)/(\d+)"
)


@dataclass(frozen=True)
class LligaGrup:
    """Un grup dins d'una divisió de lliga."""

    lliga_id: int
    divisio_id: int
    grup_id: int
    nom: str  # "GRUP A", "HONOR FINAL", ...
    club_responsable: str | None = None


def parse_lliga_grups(html: str) -> list[LligaGrup]:
    """Parseja /ca/lligues/grups/{lliga}/{divisio} → llista de grups.

    Estructura: cada grup és una fila amb tres divs (nom, responsable, link
    de classificació). El nom del grup ve del text del link "jornades",
    i el lliga_id/divisio_id/grup_id es deriven de l'href.
    """
    soup = BeautifulSoup(html, "lxml")
    section = soup.select_one("section.three.fourths.padded")
    if section is None:
        raise ValueError("Secció principal no trobada a la pàgina de grups")

    out: list[LligaGrup] = []
    # Cada grup és un <div class="row box info"> amb un <a> que apunta a
    # ca/lligues/jornades/...
    for box in section.select("div.row.box.info"):
        link = box.select_one("a[href]")
        if link is None:
            continue
        m = _LLIGA_GRUP_HREF_RE.search(link["href"])
        if m is None:
            continue
        # Responsable: el segon dels 3 divs "four twelfths".
        cells = box.select("div.four.twelfths")
        responsable: str | None = None
        if len(cells) >= 2:
            responsable = cells[1].get_text(strip=True) or None
        out.append(
            LligaGrup(
                lliga_id=int(m.group(1)),
                divisio_id=int(m.group(2)),
                grup_id=int(m.group(3)),
                nom=_text(link).upper(),
                club_responsable=responsable,
            )
        )
    return out


@dataclass(frozen=True)
class LligaJornadaLink:
    """Link a una jornada concreta dins d'un grup."""

    lliga_id: int
    divisio_id: int
    grup_id: int
    jornada_id: int
    nom: str  # "Jornada 01"
    data: date | None


# Patró d'href per a grups d'una divisió: ca/lligues/grups/{lliga}/{divisio}
_LLIGA_GRUPS_HREF_RE = re.compile(
    r"lligues/grups/(\d+)/(\d+)"
)

# Patró d'href per a jornades: ca/lligues/encontres/{lliga}/{divisio}/{grup}/{jornada}
_LLIGA_ENCONTRES_HREF_RE = re.compile(
    r"lligues/encontres/(\d+)/(\d+)/(\d+)/(\d+)"
)


@dataclass(frozen=True)
class LligaDivisio:
    """Una divisió dins d'una lliga (HONOR, 1a, 2a, ...)."""

    lliga_id: int
    divisio_id: int
    nom: str


@dataclass(frozen=True)
class ClubOficial:
    """Una fila del listing oficial de clubs (/ca/clubs/5/Federacio).

    El portal NO exposa un id intern per al club, així doncs el nom és l'únic
    identificador. Per al schema usem el nom com a `fcb_id`.
    """

    nom: str
    telefon: str | None = None
    email: str | None = None
    direccio: str | None = None
    web: str | None = None


def parse_clubs_listing(html: str) -> list[ClubOficial]:
    """Parseja /ca/clubs/5/Federacio → llista de clubs amb dades de contacte.

    Estructura: <table> amb capçalera CLUB/TELÈFON/EMAIL/DIRECCIÓ/WEB.
    """
    soup = BeautifulSoup(html, "lxml")
    section = soup.select_one("section.three.fourths.padded")
    if section is None:
        raise ValueError("Secció principal no trobada al listing de clubs")
    table = section.find("table")
    if table is None:
        raise ValueError("Taula no trobada al listing de clubs")
    out: list[ClubOficial] = []
    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < 4:
            continue  # capçalera o filera incompleta
        nom = _text(cells[0])
        if not nom:
            continue
        out.append(
            ClubOficial(
                nom=nom,
                telefon=_text(cells[1]) or None,
                email=_text(cells[2]) or None,
                direccio=_text(cells[3]) or None,
                web=_text(cells[4]) if len(cells) >= 5 else None,
            )
        )
    return out


def parse_lliga_divisions(html: str) -> list[LligaDivisio]:
    """Parseja /ca/lligues/divisions/{lliga} → llista de divisions."""
    soup = BeautifulSoup(html, "lxml")
    section = soup.select_one("section.three.fourths.padded")
    if section is None:
        raise ValueError("Secció principal no trobada a la pàgina de divisions")
    out: list[LligaDivisio] = []
    for link in section.select("a[href]"):
        m = _LLIGA_GRUPS_HREF_RE.search(link["href"])
        if m is None:
            continue
        out.append(
            LligaDivisio(
                lliga_id=int(m.group(1)),
                divisio_id=int(m.group(2)),
                nom=_text(link).upper(),
            )
        )
    return out


def parse_lliga_jornades(html: str) -> list[LligaJornadaLink]:
    """Parseja /ca/lligues/jornades/{lliga}/{divisio}/{grup} → llista de jornades."""
    soup = BeautifulSoup(html, "lxml")
    section = soup.select_one("section.three.fourths.padded")
    if section is None:
        raise ValueError("Secció principal no trobada a la pàgina de jornades")
    out: list[LligaJornadaLink] = []
    for box in section.select("div.row.box.info"):
        link = box.select_one("a[href]")
        if link is None:
            continue
        m = _LLIGA_ENCONTRES_HREF_RE.search(link["href"])
        if m is None:
            continue
        # Data: dins d'un <b> a la segona cel·la.
        data_val: date | None = None
        b = box.select_one("div.six.twelfths.mobile + div.six.twelfths.mobile b")
        if b is not None:
            try:
                data_val = date.fromisoformat(_text(b))
            except ValueError:
                data_val = None
        out.append(
            LligaJornadaLink(
                lliga_id=int(m.group(1)),
                divisio_id=int(m.group(2)),
                grup_id=int(m.group(3)),
                jornada_id=int(m.group(4)),
                nom=_text(link),
                data=data_val,
            )
        )
    return out


@dataclass(frozen=True)
class LligaEncontre:
    """Un encontre dins d'una jornada: equip local vs equip visitant amb resultat."""

    lliga_id: int
    divisio_id: int
    grup_id: int
    jornada_id: int
    encontre_id: int
    equip_local: str
    p_parcials_local: int | None
    p_match_local: int | None
    equip_visitant: str
    p_parcials_visitant: int | None
    p_match_visitant: int | None


_P_VALUE_RE = re.compile(r"<b>\s*(\d+)\s*</b>")


def parse_lliga_encontres(html: str) -> list[LligaEncontre]:
    """Parseja /ca/lligues/encontres/{lliga}/{divisio}/{grup}/{jornada}."""
    soup = BeautifulSoup(html, "lxml")
    section = soup.select_one("section.three.fourths.padded")
    if section is None:
        raise ValueError("Secció principal no trobada a la pàgina d'encontres")
    out: list[LligaEncontre] = []
    for box in section.select("div.row.box.info"):
        link = box.select_one("a[href]")
        if link is None:
            continue
        m = _LLIGA_PARTIDES_HREF_RE.search(link["href"])
        if m is None:
            continue
        cells = box.select("div.six.twelfths")
        if len(cells) < 4:
            continue
        equip_local = _text(cells[0])
        equip_visitant = _text(cells[2])
        p_parcials_local, p_match_local = _extract_parcials_match(str(cells[1]))
        p_parcials_visitant, p_match_visitant = _extract_parcials_match(str(cells[3]))
        out.append(
            LligaEncontre(
                lliga_id=int(m.group(1)),
                divisio_id=int(m.group(2)),
                grup_id=int(m.group(3)),
                jornada_id=int(m.group(4)),
                encontre_id=int(m.group(5)),
                equip_local=equip_local,
                p_parcials_local=p_parcials_local,
                p_match_local=p_match_local,
                equip_visitant=equip_visitant,
                p_parcials_visitant=p_parcials_visitant,
                p_match_visitant=p_match_visitant,
            )
        )
    return out


def _extract_parcials_match(cell_html: str) -> tuple[int | None, int | None]:
    """Cel·la del tipus 'P. Parcials <b>5</b> P. Match <b>3</b>'."""
    values = _P_VALUE_RE.findall(cell_html)
    parcials = int(values[0]) if len(values) >= 1 else None
    match = int(values[1]) if len(values) >= 2 else None
    return parcials, match


@dataclass(frozen=True)
class LligaPartidaRow:
    """Una partida individual dins d'un encontre de lliga, amb camps rics."""

    data_partida: date | None
    modalitat: str  # "Tres bandes", "Lliure", ...
    local_nom: str
    local_caramboles: int | None
    local_serie_major: int | None
    local_punts: int | None
    visitant_nom: str
    visitant_caramboles: int | None
    visitant_serie_major: int | None
    visitant_punts: int | None
    entrades: int | None
    arbitre: str | None
    assistencia: str | None


def parse_lliga_partides(html: str) -> list[LligaPartidaRow]:
    """Parseja /ca/lligues/partides/.../{encontre} → llista de partides individuals.

    Cada partida és un `<div class="row box info padded">` amb camps dins de
    `<div class="three ninths">` (noms) i `<div class="two ninths">` (la resta).
    La data NO sortia inline a la fixture observada; els tests la deixen None.
    """
    soup = BeautifulSoup(html, "lxml")
    section = soup.select_one("section.three.fourths.padded")
    if section is None:
        raise ValueError("Secció principal no trobada a la pàgina de partides de lliga")

    out: list[LligaPartidaRow] = []
    for box in section.select("div.row.box.info.padded"):
        kv = _extract_partida_kv(box)
        if "Local" not in kv or "Visitant" not in kv:
            continue
        local = kv["Local"]
        visitant = kv["Visitant"]
        out.append(
            LligaPartidaRow(
                data_partida=kv.get("data"),
                modalitat=kv.get("Modalitat", ""),
                local_nom=local["nom"],
                local_caramboles=local.get("Caramboles"),
                local_serie_major=local.get("Sèrie major"),
                local_punts=local.get("Punts"),
                visitant_nom=visitant["nom"],
                visitant_caramboles=visitant.get("Caramboles"),
                visitant_serie_major=visitant.get("Sèrie major"),
                visitant_punts=visitant.get("Punts"),
                entrades=kv.get("Entrades"),
                arbitre=kv.get("Àrbitre"),
                assistencia=kv.get("Assistència"),
            )
        )
    return out


def _extract_partida_kv(box: Tag) -> dict:
    """Extreu un dict 'flat' dels camps d'un box de partida de lliga.

    L'HTML segueix l'ordre:
      - 1r .three.ninths = nom Local (sense label, només <b>NOM</b>)
      - 3 .two.ninths = Caramboles/Sèrie major/Punts del local
      - 1r .three.ninths = nom Visitant
      - 3 .two.ninths = camps del visitant
      - .three.ninths Entrades + .two.ninths Àrbitre + .two.ninths Assistència + .two.ninths Modalitat

    Retornem un dict amb les claus Local i Visitant (dicts amb nom+stats) i
    els camps generals com a clau-valor simple.
    """
    name_cells = box.select("div.three.ninths")
    stat_cells = box.select("div.two.ninths")
    kv: dict = {}
    if len(name_cells) < 2:
        return kv
    # Local: nom (primera three.ninths) + primeres 3 two.ninths (Caramboles, Sèrie, Punts).
    local = {"nom": _text(name_cells[0].find("b") or name_cells[0])}
    for cell in stat_cells[:3]:
        k, v = _parse_labelled_cell(cell)
        if k:
            local[k] = v
    # Visitant: nom (segona three.ninths) + següents 3 two.ninths.
    visitant = {"nom": _text(name_cells[1].find("b") or name_cells[1])}
    for cell in stat_cells[3:6]:
        k, v = _parse_labelled_cell(cell)
        if k:
            visitant[k] = v
    kv["Local"] = local
    kv["Visitant"] = visitant
    # Camps generals: Entrades (3a three.ninths), més les two.ninths restants.
    if len(name_cells) >= 3:
        k, v = _parse_labelled_cell(name_cells[2])
        if k:
            kv[k] = v
    for cell in stat_cells[6:]:
        k, v = _parse_labelled_cell(cell)
        if k:
            kv[k] = v
    return kv


def _parse_labelled_cell(cell: Tag) -> tuple[str | None, object]:
    """Cel·la del tipus `<b>Caramboles</b> 40` o `<b>Àrbitre</b> BOTERO`."""
    b = cell.find("b")
    if b is None:
        return None, None
    label = _text(b)
    # El valor és tot el text de la cel·la menys l'etiqueta.
    full = cell.get_text(separator=" ", strip=True)
    value_str = full[len(label):].strip()
    # Camps numèrics:
    if label in {"Caramboles", "Sèrie major", "Punts", "Entrades"}:
        return label, _parse_int(value_str)
    return label, value_str or None


def _parse_partida_row(cells: list[Tag], competicio: str) -> RawGameRow:
    data_str = _text(cells[0])
    try:
        data_val = date.fromisoformat(data_str)
    except ValueError as e:
        raise _SkipRow(f"data no parsejable: {data_str!r}") from e
    return RawGameRow(
        data_partida=data_val,
        competicio=competicio,
        local_nom=_text(cells[1]),
        local_punts=_parse_int(_text(cells[2])),
        local_caramboles=_parse_int(_text(cells[3])),
        visitant_nom=_text(cells[4]),
        visitant_punts=_parse_int(_text(cells[5])),
        visitant_caramboles=_parse_int(_text(cells[6])),
        entrades=_parse_int(_text(cells[7])),
    )
