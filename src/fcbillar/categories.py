"""Normalització dels noms de categoria de lliga (divisió i grup) a forma CURTA.

Les dades vénen de la federació amb formes barrejades per a la mateixa categoria:
"1a DIVISIÓ" / "1ª DIVISIÓ" / "1º DIVISIÓ" / "1a DIVISIÒ" (Ò en lloc de Ó),
"GRUP A" vs "Grup A", "UNIC" / "ÙNIC" / "ÚNIC" / "Grup ùnic"… Aquí ho unifiquem a
una forma curta i consistent perquè totes les apps mostrin la mateixa etiqueta:

    divisió:  1a · 2a · 3a · 4a · 5a · Honor · L'Amistat · Única
    grup:     A · B · C · D · Únic · Final · Promoció 1 · Promoció 2 ·
              Semifinals A · Final Four A

La divisió viu a la seva columna, així que el grup NO repeteix la divisió
("FINAL 4a DIVISIÓ" → grup "Final", amb divisió "4a" a part).
"""

from __future__ import annotations

import re
import unicodedata


def _ascii_upper(s: str) -> str:
    """Majúscules sense accents, per fer matching robust de variants."""
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return s.upper().strip()


def norm_divisio(s: str | None) -> str | None:
    """Nom curt i uniforme de la divisió. Ex: '4ª DIVISIÓ' → '4a', 'HONOR' → 'Honor'."""
    if not s:
        return s
    u = _ascii_upper(s)
    m = re.match(r"(\d+)\s*[ªºAO]?\s*DIVISI", u)
    if m:
        return f"{m.group(1)}a"
    if u.startswith("HONOR"):
        return "Honor"
    if "AMISTAT" in u:
        return "L'Amistat"
    if u.startswith("PROMOCI"):
        m = re.search(r"(\d+)", u)
        return f"Promoció a {m.group(1)}a" if m else "Promoció"
    if u.startswith("UNIC"):  # divisió "ÚNICA"
        return "Única"
    # Fallback: Caixa de títol conservant accents de l'original.
    return s.strip().capitalize()


def norm_grup(s: str | None) -> str | None:
    """Nom curt i uniforme del grup/fase. Ex: 'FINAL 4a DIVISIÓ' → 'Final', 'GRUP A' → 'A'."""
    if not s:
        return s
    u = _ascii_upper(s)
    if "FINAL FOUR" in u:
        m = re.search(r"([A-D])\b", u.split("FOUR", 1)[1])
        return f"Final Four {m.group(1)}" if m else "Final Four"
    if u.startswith("FINAL"):
        return "Final"
    if u.startswith("SEMIFINAL"):
        m = re.search(r"([A-D])", u.split("SEMIFINAL", 1)[1])
        return f"Semifinals {m.group(1)}" if m else "Semifinals"
    if u.startswith("PROMOCI"):
        m = re.search(r"(\d+)", u)
        if m:
            return f"Promoció {m.group(1)}"
        if "HONOR" in u:
            return "Promoció Honor"
        if "PRIMERA" in u:
            return "Promoció Primera"
        return "Promoció"
    if "UNIC" in u:  # "UNIC" / "ÙNIC" / "ÚNIC" / "GRUP ÚNIC"
        return "Únic"
    m = re.match(r"GRUP\s*([A-Z])\b", u)
    if m:
        return m.group(1)
    m = re.match(r"^([A-Z])$", u)
    if m:
        return m.group(1)
    return s.strip().capitalize()


# Referència a divisió DINS d'un nom compost (Campionats de Catalunya individuals,
# p.ex. "TRES BANDES - 1ª DIVISIÓ"). Captura l'ordinal, la paraula DIVISIÓ amb
# qualsevol accent/forma, i un grup opcional ("A"/"B", amb o sense cometes).
_INLINE_DIV_RE = re.compile(
    r"(\d+)\s*[ªºAO]?\s*DIVISI[ÓOÒ](?:\s*\"?\s*([A-D])\s*\"?)?",
    re.IGNORECASE,
)


def short_divisio_inline(name: str | None) -> str | None:
    """Unifica les referències a divisió DINS d'un nom de campionat a forma curta.

    'TRES BANDES - 1ª DIVISIÓ'   → 'TRES BANDES - 1a'
    'LLIURE - 2A DIVISIÓ "A"'    → 'LLIURE - 2a A'
    'QUADRE 47/2 - 3A DIVISIÒ'   → 'QUADRE 47/2 - 3a'
    """
    if not name:
        return name

    def repl(m: re.Match) -> str:
        out = f"{m.group(1)}a"
        if m.group(2):
            out += f" {m.group(2).upper()}"
        return out

    return _INLINE_DIV_RE.sub(repl, name).strip()
