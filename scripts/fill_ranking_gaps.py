"""Omple els forats de rànquings (113-120) detectats per modalitat."""

from __future__ import annotations

from fcbillar.config import get_settings
from fcbillar.pipeline import ingest_ranking
from fcbillar.scraper.client import ScraperClient

# Forats: 3 bandes només 113; la resta 113-120.
COMBOS = [(113, 1)] + [(s, m) for m in (2, 3, 4, 6) for s in range(113, 121)]


def main() -> None:
    s = get_settings()
    ok = 0
    with ScraperClient(s) as cl:
        for seq, mod in COMBOS:
            try:
                ingest_ranking(cl, seq, mod, settings=s)
                ok += 1
                print(f"#{seq}/mod{mod}: OK", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"#{seq}/mod{mod}: ERROR {e}", flush=True)
    print(f"FET ({ok}/{len(COMBOS)})", flush=True)


if __name__ == "__main__":
    main()
