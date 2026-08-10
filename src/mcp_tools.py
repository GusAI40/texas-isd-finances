"""The tools an assistant can call, over the artefacts already on disk.

Every tool here is a thin read over a committed JSON file that the site already
serves and the test suite already covers. No database, no LLM, no writes, no
new data path. That is deliberate: the tools cannot be injected, cannot cost
money, and cannot go down when Supabase pauses.

The one rule that matters
-------------------------
**Every result carries the limits of the data it returns.** This project has
spent a lot of effort attaching a caveat to each number — the bond-to-results
test is "suggestive, not settled"; athletics dollars are an upper bound because
propositions bundle; a trend is a direction and not a cause. On a web page a
reader can scroll past those. In a tool result they are part of the payload, so
they travel into the model's context attached to the figure they qualify.

`structuredContent` therefore always includes `limits`, and the text block —
which is what a model actually reads most closely — states the headline
caveat in the prose rather than only in a field.

What is NOT exposed
-------------------
`/query`, the natural-language SQL endpoint. It is the one path with a
prompt-injection history (closed 2026-07-31 by running as `nlp_reader`), it
costs DeepSeek tokens against a global ceiling, and exposing it would let any
text in any chat reach a SQL agent. The tools below are deterministic lookups;
there is nothing to inject and nothing to spend.
"""
from __future__ import annotations

from typing import Any, Callable

# What an assistant is told this server is for, returned by server/discover.
INSTRUCTIONS = (
    "Authoritative Texas school district finance data, built from the Texas "
    "Education Agency's own records (PEIMS fiscal 2009-2025, TEA Snapshot, "
    "district STAAR, Comptroller property values, and 4,588 bond elections "
    "since 1958). Use find_district first to turn a district name into its "
    "six-digit TEA district number — Texas has thirteen pairs of districts "
    "that share a name, so a name alone is not an identifier. Every result "
    "carries a `limits` list describing what that data cannot show; quote "
    "those limits when you use the numbers. Nothing here supports a claim "
    "about any named individual."
)


def _api():
    """Reach the loaders in src/api.py.

    Deferred rather than module-level because api.py imports this module at
    load time; importing back at call time is what breaks the cycle without
    duplicating a second in-memory copy of a 2.8 MB artefact.
    """
    from . import api
    return api


def _need(loader: Callable[[], Any], what: str) -> Any:
    data = loader()
    if data is None:
        raise ToolError(f"The {what} dataset is not built on this deployment.")
    return data


class ToolError(Exception):
    """Something the model can fix by calling differently — a bad district
    number, an unknown name. Reported with isError so it can self-correct,
    not as a protocol error, which models rarely recover from."""


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _usd(v: Any) -> str:
    """`$-649` reads as a typo; the sign belongs in front of the currency mark.
    Operating balance is routinely negative, so this is not an edge case."""
    if v is None:
        return "unknown"
    return ("-$" if v < 0 else "$") + f"{round(abs(v)):,}"


def _big(v: Any) -> str:
    """$291,455,942,461 is unreadable and invites a model to transcribe it
    wrong. Statewide sums are quoted in billions or millions."""
    if v is None:
        return "unknown"
    a = abs(v)
    if a >= 1e9:
        return f"{'-' if v < 0 else ''}${a / 1e9:,.1f}B"
    if a >= 1e6:
        return f"{'-' if v < 0 else ''}${a / 1e6:,.1f}M"
    return _usd(v)


def _title(name: str) -> str:
    out = []
    for w in str(name or "").split():
        out.append(w.upper() if w.upper() in {"ISD", "CISD", "CSD", "CCSD", "MSD"}
                   else w.capitalize())
    return " ".join(out)


def _resolve(number: str) -> str:
    """District numbers are six-digit STRINGS. `57905` is not Dallas ISD;
    `057905` is. Models drop leading zeros constantly, so accept the mistake
    and repair it rather than 404ing on it."""
    n = str(number or "").strip()
    if n.isdigit() and len(n) < 6:
        n = n.zfill(6)
    if not (len(n) == 6 and n.isdigit()):
        raise ToolError(
            f"{number!r} is not a TEA district number. They are six digits, "
            "e.g. 057905 for Dallas ISD. Use find_district to look one up.")
    return n


# --------------------------------------------------------------------------
# tools
# --------------------------------------------------------------------------

def find_district(args: dict) -> tuple[str, dict]:
    q = str(args.get("name") or "").strip().lower()
    if len(q) < 2:
        raise ToolError("Give at least two characters of a district name.")
    data = _need(_api()._fallback_index, "district index")
    rows = data.get("districts", [])
    starts = [r for r in rows if str(r["district_name"]).lower().startswith(q)]
    contains = [r for r in rows if q in str(r["district_name"]).lower()
                and r not in starts]
    hits = (starts + contains)[:12]
    if not hits:
        raise ToolError(f"No Texas district matches {args.get('name')!r}.")
    # Enrolment is what lets a model pick between two districts of the same
    # name. Without it the warning below tells it there is a problem and gives
    # it no way to resolve it.
    sizes = {}
    forensic = _api()._forensics()
    if forensic:
        sizes = {r["n"]: r.get("students") for r in forensic.get("table", [])}
    out = [{"district_number": r["district_number"],
            "district_name": _title(r["district_name"]),
            "students": sizes.get(r["district_number"])} for r in hits]
    lines = "\n".join(
        f"  {r['district_number']}  {r['district_name']}"
        + (f"  ({r['students']:,} students)" if r["students"] else "")
        for r in out)
    text = (f"{len(out)} district(s) matching {args.get('name')!r}:\n{lines}\n\n"
            "Texas has thirteen pairs of districts sharing a name (two Wylie ISDs, "
            "two Highland Park ISDs, two Northside ISDs and more), so confirm which "
            "one is meant before quoting figures.")
    return text, {"matches": out, "limits": [
        "A district name is not an identifier in Texas — thirteen names are "
        "shared by two districts each. Use the district_number.",
    ]}


def district_money(args: dict) -> tuple[str, dict]:
    num = _resolve(args.get("district_number"))
    data = _need(_api()._economics, "economics")
    rec = data["districts"].get(num)
    if rec is None:
        raise ToolError(f"District {num} is not in the finance dataset.")
    a, r, t = rec.get("allocation") or {}, rec.get("revenue") or {}, rec.get("tax") or {}
    name = _title(rec.get("district_name", num))
    text = (
        f"{name} ({num}), fiscal {rec.get('year')}, {rec.get('students'):,} students.\n"
        f"Spends {_usd(a.get('total_per_student'))} per student in total: "
        f"{_usd(a.get('operating_per_student'))} operating plus "
        f"{_usd(a.get('debt_per_student'))} servicing debt. Debt service is NOT in "
        f"TEA's operating figure, so the two are composed here, never subtracted.\n"
        f"Instruction: {_usd(a.get('instruction_per_student'))} per student.\n"
        f"Revenue: {r.get('local_pct')}% local, {r.get('state_pct')}% state, "
        f"{r.get('federal_pct')}% federal — local measured on GROSS property "
        f"collections before recapture is deducted.\n"
        + (f"School tax on a $300,000 home: {_usd(t.get('bill_on_home'))}"
           + (f", of which {_usd(t.get('leaves_district'))} leaves the district "
              "under recapture.\n" if t.get("leaves_district") else ".\n")
           if t.get("bill_on_home") else "This district levies no property tax.\n"))
    return text, {**rec, "limits": data["meta"].get("limits", [])}


def district_forensics(args: dict) -> tuple[str, dict]:
    num = _resolve(args.get("district_number"))
    data = _need(_api()._forensics, "forensic")
    rec = data["districts"].get(num)
    if rec is None:
        raise ToolError(f"District {num} is not in the forensic dataset.")
    o, p = rec.get("outside_operating") or {}, rec.get("who_pays") or {}
    b, land = rec.get("ballot") or {}, rec.get("where_it_landed") or {}
    name = _title(rec.get("district_name", num))
    flags = rec.get("flags") or []
    text = (
        f"{name} ({num}) — the four money questions Texas reports separately.\n"
        f"1. OUTSIDE the operating total: {_usd(o.get('per_student'))} per student a "
        f"year in debt service, higher than {o.get('percentile')}% of Texas districts "
        f"(state median {_usd(o.get('state_median'))}).\n"
        f"2. WHO PAYS: {p.get('local_pct')}c of every revenue dollar is raised locally "
        f"against {p.get('state_local_pct')}c statewide, on gross collections.\n"
        + (f"3. THE BALLOT: {_big(b.get('approved'))} approved by voters across "
           f"{b.get('props')} propositions since {b.get('first_year')}; "
           f"{b.get('athletics_share_pct')}% of what was asked named athletics — an "
           f"UPPER BOUND, because propositions bundle purposes.\n"
           if b else "3. THE BALLOT: no bond election on record.\n")
        + (f"4. WHERE IT LANDED: {land.get('actual')}% at Meets against "
           f"{land.get('expected')}% predicted by this district's own student need "
           f"({land.get('gap'):+.1f} points).\n" if land else "")
        + ("\nWhat stands out:\n" + "\n".join(
            f"  - {f['label']}: {f['detail']}" for f in flags) if flags else "")
        + "\n\nThese are descriptions of published numbers against published "
          "thresholds, not findings of wrongdoing, and there is deliberately no "
          "combined score."
    )
    return text, {**rec, "thresholds": data["meta"].get("thresholds", {}),
                  "limits": data["meta"].get("limits", [])}


def district_trends(args: dict) -> tuple[str, dict]:
    num = _resolve(args.get("district_number"))
    data = _need(_api()._trends, "trend")
    rec = data["districts"].get(num)
    if rec is None:
        raise ToolError(
            f"District {num} has no trend. Districts reporting fewer than eight of "
            "the seventeen years are excluded — too little to call a trend.")
    m = data["meta"]["measures"]
    name = _title(rec.get("district_name", num))
    lines = []
    for key, cfg in m.items():
        ch, vs = (rec["change"] or {}).get(key), (rec["vs_state"] or {}).get(key)
        if not ch:
            continue
        unit = cfg["unit"]
        fmt = (lambda v: f"{v:.1f}%") if unit == "%" else _usd
        steep = (" — moving that way faster than Texas as a whole"
                 if vs and vs.get("steeper_than_state") else "")
        lines.append(f"  {cfg['label']}: {fmt(ch['first'])} -> {fmt(ch['last'])}{steep}")
    text = (f"{name} ({num}), fiscal {data['meta']['first_year']}-"
            f"{data['meta']['last_year']}, constant 2024 dollars:\n"
            + "\n".join(lines)
            + ("\n\nNOTE: fewer than 500 students, so per-student figures swing on a "
               "single hire or retirement. Read the direction, not the size."
               if rec.get("small_district") else "")
            + "\n\nA trend is a direction, not a cause: a falling instruction share "
              "can be a district cutting classrooms or opening them, and this data "
              "cannot tell the two apart.")
    return text, {**rec, "limits": data["meta"].get("limits", [])}


def district_bonds(args: dict) -> tuple[str, dict]:
    num = _resolve(args.get("district_number"))
    data = _need(_api()._bonds, "bond")
    rec = data["districts"].get(num)
    if rec is None:
        raise ToolError(
            f"District {num} has no bond election on record. Districts that never "
            "went to voters for building debt have no entry.")
    t = rec["totals"]
    name = _title(rec.get("district_name", num))
    recent = rec["elections"][-5:]
    text = (
        f"{name} ({num}) put {t['props']} bond propositions to voters between "
        f"{t['first_year']} and {t['last_year']}; {t['passed']} carried "
        f"({t['pass_rate']}%). Asked {_usd(t['asked'])}, approved "
        f"{_usd(t['approved'])}.\nMost recent:\n"
        + "\n".join(f"  {e['date']}  {_big(e['amount'])}  "
                    f"{'carried' if e['passed'] else 'defeated'}  {e['purpose']}"
                    for e in recent)
        + "\n\nThe ballot is the only public record of what school debt was FOR — TEA "
          "does not itemise facilities. Amounts are as asked, in the dollars of their "
          "own year, and are not inflation-adjusted."
    )
    return text, {**rec, "limits": data["meta"].get("limits", [])}


def texas_overview(args: dict) -> tuple[str, dict]:
    f = _need(_api()._forensics, "forensic")
    t = _need(_api()._trends, "trend")
    s, w = f["statewide"], f["statewide"].get("did_it_work") or {}
    findings = t["findings"]
    text = (
        f"Texas school finance, {s['districts']:,} districts.\n"
        f"Debt service OUTSIDE TEA's operating total: "
        f"${s['debt_total'] / 1e9:,.1f}B a year, median {_usd(s['debt_median'])} per "
        f"student.\nWho pays: {s['revenue']['local_pct']}c local, "
        f"{s['revenue']['state_pct']}c state, {s['revenue']['federal_pct']}c federal, "
        f"on gross collections. {s['recapture_payers']:,} districts pay recapture.\n"
        f"Ballot record: {s['ballot']['propositions']:,} propositions since 1958, "
        f"{_big(s['ballot']['asked'])} asked, {_big(s['ballot']['approved'])} approved.\n"
        f"\nSeventeen years (fiscal {t['meta']['first_year']}-{t['meta']['last_year']}, "
        f"constant 2024 dollars):\n"
        + "\n".join(f"  {x['headline']}: {x['figure']}" for x in findings)
        + (f"\n\nDid passing a bond change results? {w.get('difference'):+.2f} points, "
           f"CI {w.get('ci_low'):+.2f} to {w.get('ci_high'):+.2f}, p={w.get('p_value')}"
           + (" — SUGGESTIVE, NOT SETTLED. It crossed the conventional line only when "
              "a district-matching bug was fixed. Do not report it as proof that bonds "
              "raise test scores." if w.get("fragile") else ".") if w else "")
    )
    return text, {
        "statewide": s, "trend_findings": findings,
        "trend_change": t["statewide"]["change"],
        "deficit_by_year": t["statewide"]["deficit_by_year"],
        "balanced_panel_check": t["meta"]["balanced_panel_check"],
        "limits": f["meta"].get("limits", []) + t["meta"].get("limits", []),
    }


def compare_districts(args: dict) -> tuple[str, dict]:
    nums = args.get("district_numbers") or []
    if not isinstance(nums, list) or not (2 <= len(nums) <= 6):
        raise ToolError("Give between 2 and 6 district numbers to compare.")
    data = _need(_api()._forensics, "forensic")
    rows, missing = [], []
    for raw in nums:
        try:
            n = _resolve(raw)
        except ToolError:
            missing.append(str(raw))
            continue
        rec = data["districts"].get(n)
        if rec is None:
            missing.append(n)
            continue
        o = rec.get("outside_operating") or {}
        p = rec.get("who_pays") or {}
        land = rec.get("where_it_landed") or {}
        rows.append({
            "district_number": n, "district_name": _title(rec.get("district_name", n)),
            "students": rec.get("students"),
            "debt_per_student": o.get("per_student"),
            "operating_per_student": o.get("operating_per_student"),
            "local_pct": p.get("local_pct"),
            "tax_on_300k_home": p.get("tax_bill_on_home"),
            "recapture_per_student": p.get("recapture_per_student"),
            "points_vs_predicted": land.get("gap"),
        })
    if not rows:
        raise ToolError("None of those district numbers are in the dataset: "
                        + ", ".join(missing))
    def _gap(v: Any) -> str:
        return "—" if v is None else f"{v:+.1f}"

    head = (f"{'District':28}{'Students':>9}{'Debt/stu':>10}"
            f"{'Oper/stu':>10}{'Local%':>8}{'vs pred':>9}")
    body = "\n".join(
        f"{r['district_name'][:27]:28}{(r['students'] or 0):>9,}"
        f"{_usd(r['debt_per_student']):>10}{_usd(r['operating_per_student']):>10}"
        f"{(r['local_pct'] if r['local_pct'] is not None else 0):>7}%"
        f"{_gap(r['points_vs_predicted']):>9}"
        for r in rows)
    text = (head + "\n" + body
            + ("\n\nNot found: " + ", ".join(missing) if missing else "")
            + "\n\n'vs pred' is percentage points at the Meets bar against what each "
              "district's OWN poverty, emergent-bilingual and special-education rates "
              "predict — not against the state, which mostly measures poverty. Debt "
              "per student sits outside TEA's operating total.")
    return text, {"districts": rows, "not_found": missing,
                  "limits": data["meta"].get("limits", [])}


# --------------------------------------------------------------------------
# registry
# --------------------------------------------------------------------------
# `x-mcp-header` mirrors district_number into an Mcp-Param-District header, so
# an intermediary can route or rate-limit per district without parsing the
# body. It is only valid on primitives reachable through `properties` keys,
# which is why the compare tool's array argument carries no annotation.
_DISTRICT_ARG = {
    "type": "string",
    "description": ("Six-digit TEA district number, e.g. 057905 for Dallas ISD. "
                    "Leading zeros matter. Use find_district to look one up."),
    "pattern": "^[0-9]{6}$",
    "x-mcp-header": "District",
}

TOOLS: list[dict] = [
    {
        "name": "find_district",
        "title": "Find a Texas school district",
        "description": ("Turn a district name into its six-digit TEA district number. "
                        "Call this first: Texas has thirteen pairs of districts that "
                        "share a name, so a name alone cannot identify one."),
        "inputSchema": {
            "type": "object",
            "properties": {"name": {
                "type": "string", "minLength": 2,
                "description": "Part of a district name, e.g. 'Dallas' or 'Wylie'."}},
            "required": ["name"],
            "additionalProperties": False,
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "matches": {"type": "array", "items": {
                    "type": "object",
                    "properties": {"district_number": {"type": "string"},
                                   "district_name": {"type": "string"},
                                   "students": {"type": ["integer", "null"]}},
                    "required": ["district_number", "district_name"]}},
                "limits": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["matches", "limits"],
        },
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
        "handler": find_district,
    },
    {
        "name": "district_money",
        "title": "What a district raises and spends",
        "description": ("Per-student spending split between operations and debt "
                        "service, the local/state/federal revenue mix measured on "
                        "GROSS property collections, and the school tax on a $300,000 "
                        "home including what leaves under recapture."),
        "inputSchema": {"type": "object", "properties": {"district_number": _DISTRICT_ARG},
                        "required": ["district_number"], "additionalProperties": False},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
        "handler": district_money,
    },
    {
        "name": "district_forensics",
        "title": "The four money questions Texas reports separately",
        "description": ("What sits OUTSIDE TEA's operating total (debt service), who "
                        "actually pays before recapture is deducted, what the ballot "
                        "said the debt was for, and where results landed against what "
                        "the district's own student need predicts. Returns descriptive "
                        "flags with the published threshold behind each one."),
        "inputSchema": {"type": "object", "properties": {"district_number": _DISTRICT_ARG},
                        "required": ["district_number"], "additionalProperties": False},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
        "handler": district_forensics,
    },
    {
        "name": "district_trends",
        "title": "Seventeen years, and which way a district is moving",
        "description": ("Fiscal 2009-2025 in constant 2024 dollars: instruction's "
                        "share of the operating dollar, instruction per student, debt "
                        "service, security, operating balance and federal revenue — "
                        "each against the statewide line, with a flag when the "
                        "district is moving the worrying way faster than Texas."),
        "inputSchema": {"type": "object", "properties": {"district_number": _DISTRICT_ARG},
                        "required": ["district_number"], "additionalProperties": False},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
        "handler": district_trends,
    },
    {
        "name": "district_bonds",
        "title": "Every bond a district put on a ballot",
        "description": ("All decided bond propositions 1958-2024 with date, stated "
                        "purpose, amount, and whether voters carried or defeated it. "
                        "The ballot is the only public record of what school debt was "
                        "for — TEA does not itemise facilities."),
        "inputSchema": {"type": "object", "properties": {"district_number": _DISTRICT_ARG},
                        "required": ["district_number"], "additionalProperties": False},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
        "handler": district_bonds,
    },
    {
        "name": "texas_overview",
        "title": "Statewide Texas school finance and the seventeen-year trend",
        "description": ("Statewide totals plus the six measured trends: instruction's "
                        "falling share of the operating dollar, rising debt service "
                        "and security, the federal funding cliff, the first statewide "
                        "operating deficit in the window, and stalled enrolment "
                        "growth. Includes the balanced-panel robustness check."),
        "inputSchema": {"type": "object", "additionalProperties": False},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
        "handler": texas_overview,
    },
    {
        "name": "compare_districts",
        "title": "Compare districts side by side",
        "description": ("Two to six districts on students, debt service per student, "
                        "operating spend per student, local revenue share, the tax on "
                        "a $300,000 home, and points above or below what each "
                        "district's own student need predicts."),
        "inputSchema": {
            "type": "object",
            "properties": {"district_numbers": {
                "type": "array", "minItems": 2, "maxItems": 6,
                "items": {"type": "string", "pattern": "^[0-9]{6}$"},
                "description": "Six-digit TEA district numbers."}},
            "required": ["district_numbers"], "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
        "handler": compare_districts,
    },
]

_BY_NAME = {t["name"]: t for t in TOOLS}


def list_tools() -> list[dict]:
    """The wire form: same order every time, so clients can cache the list and
    model prompt caches keep hitting."""
    return [{k: v for k, v in t.items() if k != "handler"} for t in TOOLS]


def call_tool(name: str, args: dict) -> dict:
    """Raises KeyError for an unknown tool — a protocol error. Anything the
    model could fix by calling differently comes back as isError instead."""
    tool = _BY_NAME[name]
    try:
        text, structured = tool["handler"](args)
    except ToolError as e:
        return {"content": [{"type": "text", "text": str(e)}], "isError": True}
    except Exception as e:  # a bug here must not look like a data finding
        return {"content": [{"type": "text",
                             "text": f"{name} failed: {type(e).__name__}"}],
                "isError": True}
    return {
        "content": [{"type": "text", "text": text}],
        "structuredContent": structured,
        "isError": False,
    }
