"""Resolve a district NAME written by somebody else to a TEA district number.

Every dataset in this project except TEA's own carries district names, not
numbers, and a name is not an identifier. Texas has two Wylie ISDs, two
Highland Park ISDs, two Northside ISDs — thirteen colliding pairs in all — and
the source files disambiguate them with a trailing lowercase letter ("Wylie
ISDa", "Wylie ISDb") that no naive normaliser understands. Districts also
rename themselves: Roscoe ISD is now Roscoe Collegiate ISD, Rio Grande City
CISD is now Rio Grande City Grulla ISD, and TEA's own file spells Stephenville
with no "ISD" at all.

Matching on a squashed uppercase name therefore fails in two directions, and
only one of them is visible:

- SILENT DROP — 147 propositions, including twenty in Wylie ISD, were simply
  absent from the published bond history because "WYLIEISDA" is not "WYLIEISD".
  A district page showed no ballot history for a district that had twenty.
- WRONG DISTRICT — "S and S CISD" (Grayson) and "Sands CISD" (Dawson) both
  squash to "SANDSCISD", so whichever TEA row sorted first collected the
  other's elections. That is a published claim attached to the wrong district,
  which is the worst failure this project can have.

The fix is that a TEA district number already contains its county: the first
three digits are the county code (057 = Dallas, so 057905 is Dallas ISD). The
bond file records the county of each election. County plus a stemmed name is
unique, and where it is not, this refuses to guess.

Resolution order, most trustworthy first, and the method is recorded on every
row so the audit can list what was decided how:

1. ``name+county``  — stemmed name matches, and the county matches. Exact.
2. ``name``         — stemmed name matches exactly one TEA district statewide.
3. ``prefix+county``— inside the right county, exactly one TEA district's stem
                      is a prefix of the source's, or vice versa (this is what
                      a rename looks like). Requires 6+ characters, refuses on
                      any ambiguity, and every such match is printed by
                      ``scripts/audit_bond_match.py`` for a human to read.
4. unmatched        — counted and named, never guessed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# Words that describe the KIND of district rather than which one it is. TEA,
# the bond file and the Comptroller disagree about these constantly ("Pewitt
# ISD" vs "PEWITT CISD"), and none of the disagreements are real.
_TYPE_WORDS = {"ISD", "CISD", "CSD", "CCSD", "MSD", "SD", "CONS", "CONSOLIDATED"}
# Abbreviations that are always the same word.
_EXPAND = {"CO": "COUNTY"}
# "&" is a word, not punctuation, and stripping it silently changes the name.
# TEA writes "S AND S CISD"; the Bond Review Board writes "S&S CISD". Dropping
# the ampersand gives "SS" and drops the district's whole ballot history —
# which is exactly what happened when the bond file moved to the state's own
# feed. Expanded before punctuation is stripped, so both spellings stem alike.
_AMPERSAND = re.compile(r"\s*&\s*")
# Trailing words a district added when it rebranded. Dropping them lets a
# renamed district still match its own history; the county check keeps it safe.
_RENAME_SUFFIX = {"COLLEGIATE"}
# "Wylie ISDa" — a disambiguator the source appends, not part of the name.
_AB_SUFFIX = re.compile(r"(ISD|CISD|CSD|CCSD|MSD)[a-z]$")
_MIN_PREFIX = 6


def stem(name: str) -> str:
    """Squash a district name to the part that identifies WHICH district.

    Drops punctuation, the district-type word, and a rebrand suffix, so
    ``Pewitt ISD``, ``PEWITT CISD`` and ``Pewitt`` all reduce to ``PEWITT``.
    """
    s = _AB_SUFFIX.sub(r"\1", str(name or "").strip())
    s = _AMPERSAND.sub(" AND ", s)
    words = [_EXPAND.get(w, w) for w in re.sub(r"[^A-Za-z ]", " ", s).upper().split()]
    while words and (words[-1] in _TYPE_WORDS or words[-1] in _RENAME_SUFFIX):
        words.pop()
    return "".join(words)


def county_key(county: str) -> str:
    """Normalise a county name. TEA writes '234 VAN ZANDT'; the bond file
    writes 'Van Zandt'. Dropping the code and everything but letters settles
    it."""
    return re.sub(r"[^A-Z]", "", str(county or "").upper())


@dataclass
class Resolver:
    """Built once from TEA's district list, then asked about names."""

    by_name_county: dict[tuple[str, str], str] = field(default_factory=dict)
    by_name: dict[str, str] = field(default_factory=dict)
    in_county: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    ambiguous_names: set[str] = field(default_factory=set)

    @classmethod
    def from_tea(cls, districts: list[tuple[str, str]],
                 county_of_code: dict[str, str]) -> "Resolver":
        """``districts`` is (district_number, district_name); ``county_of_code``
        maps a 3-digit county code to a county name."""
        r = cls()
        seen: dict[str, str] = {}
        for num, name in districts:
            st = stem(name)
            if not st:
                continue
            ck = county_key(county_of_code.get(str(num)[:3], ""))
            if ck:
                r.by_name_county.setdefault((st, ck), num)
                r.in_county.setdefault(ck, []).append((st, num))
            if st in seen and seen[st] != num:
                r.ambiguous_names.add(st)
            seen.setdefault(st, num)
        r.by_name = {k: v for k, v in seen.items() if k not in r.ambiguous_names}
        return r

    @classmethod
    def from_crosswalk(cls, path) -> "Resolver":
        """Build from data/district_crosswalk.csv, which knows every name a
        district has ever been called.

        `from_tea` learns one name per district — whichever row pandas kept —
        and that turns out to be the EARLIEST. 64 of the 103 districts that
        renamed inside this window could not be resolved by the name they go by
        today: "Rockport-Fulton ISD" was unmatched while "Aransas County ISD"
        worked. A source using a district's current name would be silently
        dropped, which is precisely how 147 bond propositions went missing the
        first time.

        Registering current name, former names and observed aliases together
        fixes both directions. Collisions are unchanged: a name claimed by two
        districts still requires the county, and still refuses rather than
        guessing.
        """
        import csv as _csv
        path = Path(path)
        rows = list(_csv.DictReader(path.open(encoding="utf-8", newline="")))
        districts, county_of = [], {}
        for r in rows:
            num = r["district_number"]
            county_of[num[:3]] = r["county"]
            for name in ([r["district_name"]]
                         + [x for x in r["former_names"].split(" | ") if x]
                         + [x for x in r["aliases"].split(" | ") if x]):
                districts.append((num, name))
        return cls.from_tea(districts, county_of)

    def resolve(self, name: str, county: str = "") -> tuple[str | None, str]:
        """Return (district_number or None, method)."""
        st = stem(name)
        if not st:
            return None, "unmatched"
        ck = county_key(county)
        hit = self.by_name_county.get((st, ck))
        if hit:
            return hit, "name+county"
        if st in self.by_name:
            return self.by_name[st], "name"
        # A rename: the stems are prefixes of one another. Only inside the
        # right county, only when exactly one district qualifies.
        if ck:
            cand = {num for cst, num in self.in_county.get(ck, [])
                    if min(len(cst), len(st)) >= _MIN_PREFIX
                    and (cst.startswith(st) or st.startswith(cst))}
            if len(cand) == 1:
                return cand.pop(), "prefix+county"
        return None, "unmatched"
