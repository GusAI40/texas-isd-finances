"""How a published number and a district name are written. Once, in one place.

Why this module exists
----------------------
Three modules were formatting the same published figures three different ways,
and two of the three functions shared a name while meaning opposite things:

    src/mcp_tools._usd(1_500_000)      -> "$1,500,000"     exact
    scripts/isd_intel._usd(1_500_000)  -> "$2M"            rounded, and wrong

`isd_intel._usd` is an abbreviator wearing an exact formatter's name. It
rendered $1,234 as "$1K" and $1.5m as "$2M" — a third of the value gone, in a
briefing that gets emailed. Any code moved between those two modules would
silently change precision with no diff to notice.

It also still carried the sign bug that was fixed in `mcp_tools` months ago and
never propagated: `$-354` instead of `-$354`. That is what duplicated formatting
does — a fix lands in one copy and the others keep shipping the defect.

The name formatters had the same shape: `_title` in mcp_tools, `nice_name` in
isd_intel and `_district_name` in api, all producing "D'hanis ISD" and
"S And S CISD" because each had independently reimplemented title-casing and
each got the same two cases wrong.

So: one `usd`, one `big`, one `district_name`, and a test that the sign, the
precision and the apostrophes stay fixed everywhere at once.
"""
from __future__ import annotations

import re
from typing import Any

# Words in a Texas district name that are not capitalised as ordinary words.
# "S and S CISD" is a real district (Grayson County) and "S And S CISD" is
# nobody. Kept lowercase unless they open the name.
_MINOR = {"and", "of", "the", "at", "for"}
# The kind-of-district suffix, which is an initialism and always shouts.
_TYPE = {"ISD", "CISD", "CSD", "CCSD", "MSD", "SD", "JJAEP", "DAEP"}
# Roman-numeral-ish and directional fragments that must not be title-cased into
# nonsense are handled by the general rule; these are the ones that would be.
_ALWAYS_UPPER = _TYPE | {"II", "III", "IV"}

_WORD = re.compile(r"[A-Za-z][A-Za-z'’.-]*")


def usd(v: Any, *, unknown: str = "unknown") -> str:
    """An exact dollar figure, to the dollar.

    The sign goes before the currency mark. "$-354" is not how anyone writes
    money, and it shipped once because the minus came from `str(int(v))` after
    the "$" had already been concatenated.
    """
    if v is None:
        return unknown
    try:
        n = round(float(v))
    except (TypeError, ValueError):
        return unknown
    return f"{'-' if n < 0 else ''}${abs(n):,}"


def big(v: Any, *, unknown: str = "unknown") -> str:
    """An abbreviated figure for headline use: $236.7B, $1.5M, $12,345.

    One decimal is kept at every magnitude, which is the difference between
    this and the function it replaces: rounding $1.5m to "$2M" loses a third of
    the value, and it did that in published output. Below a million nothing is
    abbreviated at all, because "$1K" for $1,234 is not a rounding, it is a
    different number.
    """
    if v is None:
        return unknown
    try:
        n = float(v)
    except (TypeError, ValueError):
        return unknown
    sign = "-" if n < 0 else ""
    a = abs(n)
    if a >= 1e9:
        return f"{sign}${a / 1e9:,.1f}B"
    if a >= 1e6:
        return f"{sign}${a / 1e6:,.1f}M"
    return usd(n, unknown=unknown)


def _word(w: str, first: bool) -> str:
    up = w.upper()
    if up in _ALWAYS_UPPER:
        return up
    if not first and w.lower() in _MINOR:
        return w.lower()
    # Capitalise after an apostrophe or a hyphen too: D'Hanis, Linden-Kildare.
    # A single naive .capitalize() gives "D'hanis", which is the spelling three
    # separate copies of this function independently shipped.
    return re.sub(r"(^|['’-])([a-z])",
                  lambda m: m.group(1) + m.group(2).upper(), w.lower())


def district_name(name: Any, *, unknown: str = "") -> str:
    """TEA writes district names in caps. This is how a human reads them.

    'DALLAS ISD'             -> 'Dallas ISD'
    "D'HANIS ISD"            -> "D'Hanis ISD"
    'S AND S CISD'           -> 'S and S CISD'
    'LINDEN-KILDARE CISD'    -> 'Linden-Kildare CISD'
    """
    s = str(name or "").strip()
    if not s:
        return unknown
    # Already mixed-case input is left alone apart from the type word: a source
    # that wrote "Rio Grande City Grulla ISD" knows better than this function.
    if s != s.upper():
        return " ".join(w.upper() if w.upper() in _TYPE else w for w in s.split())
    out, first = [], True
    for tok in s.split():
        m = _WORD.match(tok)
        if not m:
            out.append(tok)
            continue
        out.append(_word(m.group(0), first) + tok[m.end():])
        first = False
    return " ".join(out)
