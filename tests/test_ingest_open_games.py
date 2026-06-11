import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "ingest_open_games.py"
SPEC = importlib.util.spec_from_file_location("ingest_open_games", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

_GAME_PAGE_RE = MODULE._GAME_PAGE_RE
_GROUP_PHASE_RE = MODULE._GROUP_PHASE_RE
linked_pages = MODULE.linked_pages


def test_linked_pages_follows_current_and_historical_routes() -> None:
    html = """
    <a href="ca/individuals/grups/53/131/219">actual</a>
    <a href="/ca/historial/grupsIndividual/53/131/219">històric</a>
    <a href="ca/historial/partideseliminatoriaIndividual/53/131/220">KO</a>
    """

    groups = linked_pages(html, _GROUP_PHASE_RE)
    games = linked_pages(html, _GAME_PAGE_RE)

    assert groups == [
        "https://www.fcbillar.cat/ca/individuals/grups/53/131/219",
        "https://www.fcbillar.cat/ca/historial/grupsIndividual/53/131/219",
    ]
    assert games == [
        "https://www.fcbillar.cat/ca/historial/partideseliminatoriaIndividual/53/131/220"
    ]


def test_linked_pages_deduplicates_links() -> None:
    html = """
    <a href="ca/historial/partidesgrupsIndividual/53/131/219/1411">final</a>
    <a href="/ca/historial/partidesgrupsIndividual/53/131/219/1411">final</a>
    """

    assert linked_pages(html, _GAME_PAGE_RE) == [
        "https://www.fcbillar.cat/ca/historial/partidesgrupsIndividual/53/131/219/1411"
    ]
