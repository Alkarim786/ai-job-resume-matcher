"""Skill extraction against a taxonomy of canonical skills and aliases.

Aliases prefixed with "!" are ambiguous in running prose ("Go", "R", "C", "Swift") so they only count
when they appear inside the resume's Skills section or in a comma/pipe-separated list line.
"""

import json
import re
from functools import lru_cache
from pathlib import Path

_DATA = Path(__file__).parent / "data" / "skills.json"
_BOUNDARY_L = r"(?<![A-Za-z0-9+#.])"
_BOUNDARY_R = r"(?![A-Za-z0-9+#]|\.[A-Za-z0-9])"


def _pattern(term: str, case_sensitive: bool) -> re.Pattern:
    body = re.escape(term).replace(r"\ ", r"[\s\-]+")
    return re.compile(_BOUNDARY_L + body + _BOUNDARY_R, 0 if case_sensitive else re.IGNORECASE)


@lru_cache
def taxonomy() -> dict[str, list[str]]:
    return json.loads(_DATA.read_text(encoding="utf-8"))


@lru_cache
def _compiled() -> list[tuple[str, list[re.Pattern], list[re.Pattern]]]:
    out = []
    for canonical, aliases in taxonomy().items():
        ambiguous = [_pattern(a[1:], True) for a in aliases if a.startswith("!")]
        # If the canonical name itself is ambiguous (go, r, c, rust, swift) it is only matched case-sensitively.
        self_ambiguous = any(a[1:].lower() == canonical for a in aliases if a.startswith("!"))
        safe = [] if self_ambiguous else [_pattern(canonical, False)]
        safe += [_pattern(a, False) for a in aliases if not a.startswith("!")]
        out.append((canonical, safe, ambiguous))
    return out


@lru_cache
def _alias_map() -> dict[str, str]:
    m = {}
    for canonical, aliases in taxonomy().items():
        m[canonical] = canonical
        for a in aliases:
            m[a.lstrip("!").lower()] = canonical
    return m


def canonical_skill(name: str) -> str | None:
    """Map a recruiter-typed skill ('Postgres', 'K8s') to its canonical taxonomy name, or None if unknown."""
    return _alias_map().get(re.sub(r"\s+", " ", name.strip().lower()))


def extract_skills(text: str, skills_section: str = "") -> list[str]:
    """Return canonical skills found in the text (sorted)."""
    found = set()
    list_lines = "\n".join(line for line in text.splitlines() if line.count(",") >= 2 or line.count("|") >= 2)
    ambiguous_scope = skills_section + "\n" + list_lines
    for canonical, safe, ambiguous in _compiled():
        if any(p.search(text) for p in safe) or any(p.search(ambiguous_scope) for p in ambiguous):
            found.add(canonical)
    return sorted(found)
