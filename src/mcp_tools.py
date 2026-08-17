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

from . import absences
from . import format as fmt

# What an assistant is told this server is for, returned by server/discover.
# The server's instructions go into the context of every assistant that
# connects, so a stale figure here is a stale figure repeated by somebody
# else's model with our name on it. This said "4,588 bond elections" for as
# long as the bond layer was stale, and kept saying it after the refresh,
# because it was a hand-typed constant that nothing checked.
#
# Counts are therefore read from the artefact rather than written down. The
# prose is fixed; the numbers in it cannot drift from what the tools serve.
_INSTRUCTIONS = (
    "Authoritative Texas school district finance data, built from the Texas "
    "Education Agency's own records (PEIMS fiscal 2009-2025, TEA Snapshot, "
    "district STAAR, Comptroller property values) and the Texas Bond Review "
    "Board's ballot record ({bonds} decided bond elections, {first}-{last}) "
    "and debt register. Use find_district first to turn a district name into "
    "its six-digit TEA district number — Texas has thirteen pairs of "
    "districts that share a name, so a name alone is not an identifier. Every "
    "result carries a `limits` list describing what that data cannot show; "
    "quote those limits when you use the numbers. Nothing here supports a "
    "claim about any named individual."
)


def instructions() -> str:
    """The connect-time description, with its figures read from the data."""
    meta = {}
    try:
        meta = (_api()._bonds() or {}).get("meta") or {}
    except Exception:                     # noqa: BLE001 — never block a connect
        pass
    return _INSTRUCTIONS.format(
        bonds=f"{meta.get('propositions'):,}" if meta.get("propositions") else "all",
        first=meta.get("first_year", 1958), last=meta.get("last_year", "today"))


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

# These lived here as local copies and drifted from the ones in the briefing
# generator — same names, different precision. They are now one implementation
# in src/format.py; the aliases stay so call sites read unchanged.
_usd = fmt.usd
_big = fmt.big
_title = fmt.district_name


class NeedsInput(Exception):
    """The call cannot proceed until a human picks between real alternatives.

    Raised only for the one ambiguity this project has actually been burned by:
    a district NAME that belongs to two districts. Texas has thirteen such
    pairs, and guessing between them is how bond history was once attributed to
    the wrong district and how one district's debt was nearly counted twice.

    This is not an error the model can fix by trying harder — both answers are
    real — so it becomes an MRTR `input_required` result rather than `isError`.
    """

    def __init__(self, key: str, message: str, schema: dict):
        super().__init__(message)
        self.key, self.message, self.schema = key, message, schema

    def as_input_request(self) -> dict:
        return {self.key: {"method": "elicitation/create",
                           "params": {"mode": "form", "message": self.message,
                                      "requestedSchema": self.schema}}}


def _candidates(name: str) -> list[dict]:
    """Districts whose name matches, with enrolment so a chooser can tell two
    identically-named districts apart."""
    q = str(name or "").strip().lower()
    data = _need(_api()._fallback_index, "district index")
    rows = [r for r in data.get("districts", [])
            if str(r["district_name"]).lower() == q
            or str(r["district_name"]).lower().startswith(q)]
    sizes = {}
    forensic = _api()._forensics()
    if forensic:
        sizes = {r["n"]: r.get("students") for r in forensic.get("table", [])}
    return [{"district_number": r["district_number"],
             "district_name": _title(r["district_name"]),
             "students": sizes.get(r["district_number"])} for r in rows]


def _resolve(number: str) -> str:
    """District numbers are six-digit STRINGS. `57905` is not Dallas ISD;
    `057905` is. Models drop leading zeros constantly, so accept the mistake
    and repair it rather than 404ing on it.

    A NAME is accepted only when it is unique statewide. Where it is not, the
    call stops and asks — see NeedsInput.
    """
    n = str(number or "").strip()
    if n.isdigit() and len(n) < 6:
        n = n.zfill(6)
    if len(n) == 6 and n.isdigit():
        return n

    hits = _candidates(n)
    if len(hits) == 1:
        return hits[0]["district_number"]
    if len(hits) > 1:
        labels = {h["district_number"]:
                  f"{h['district_name']} ({h['students']:,} students)"
                  if h["students"] else h["district_name"]
                  for h in hits}
        raise NeedsInput(
            "district_number",
            f"{n!r} matches {len(hits)} Texas districts. They are different "
            f"districts with the same name, and their figures are not "
            f"interchangeable — choose which one is meant:\n"
            + "\n".join(f"  {k}  {v}" for k, v in labels.items()),
            {"type": "object",
             "properties": {"district_number": {
                 "type": "string",
                 "enum": sorted(labels),
                 "description": "; ".join(f"{k} = {v}" for k, v in labels.items())}},
             "required": ["district_number"],
             "additionalProperties": False})
    raise ToolError(
        f"{number!r} is not a TEA district number and matches no Texas "
        "district. Numbers are six digits, e.g. 057905 for Dallas ISD. Use "
        "find_district to look one up.")


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


def district_lineage(args: dict) -> tuple[str, dict]:
    """Why is this number this number — the working, and the gate's verdict.

    This is the tool that makes the rest of them checkable rather than merely
    quotable. An assistant handed "$17,053 per student" has no way to tell a
    real figure from a fluent one; handed the numerator, the denominator, WHICH
    student count the denominator is, and whether an independent re-read of
    TEA's own file agreed, it can say so, or say that it cannot.

    The verdict travels whatever it is. UNVERIFIED and STALE are returned as
    plainly as VERIFIED — a model that only ever hears good news will report
    good news, and this project has already published a two-year-old dataset
    that every check called healthy.
    """
    from . import lineage as _lin
    from . import sources as _src

    num = _resolve(args.get("district_number"))
    data = _need(_api()._economics, "economics")
    rec = (data.get("districts") or {}).get(num)
    if rec is None:
        raise ToolError(f"District {num} is not in the finance dataset.")
    meta = data.get("meta") or {}
    lin = (rec.get("revenue") or {}).get("lineage") or {}
    figures, templates = lin.get("figures") or {}, meta.get("lineage_templates") or {}
    available = sorted(set(figures) & set(templates))
    metric = args.get("metric") or "total_per_student"
    if metric not in available:
        raise ToolError(
            f"No published working for {metric!r}. This district publishes "
            f"working for: {', '.join(available) or 'nothing yet'}. Figures "
            "without an emitted numerator and denominator cannot have one "
            "reconstructed from the rounded result.")

    raw = {**templates[metric], **figures[metric], "denominator": lin.get("denominator")}
    ev = _lin.Evidence(
        metric=raw["metric"], value=raw["value"], numerator=raw.get("numerator"),
        denominator=raw.get("denominator"),
        denominator_type=raw.get("denominator_type", ""),
        formula=raw.get("formula", ""), unit=raw.get("unit", ""),
        rounding=raw.get("rounding", 0.5), fiscal_year=raw.get("fiscal_year"),
        district_number=num, source=raw.get("source", ""),
        source_url=(_src.SOURCES.get(raw.get("source_id", "")) or {}).get("url", ""),
        artifact=raw.get("artifact", ""), source_vintage=str(meta.get("year", "")),
        notes=[raw["source_note"]] if raw.get("source_note") else [],
        recomputed_value=raw.get("recomputed_value"),
        recomputed_from=lin.get("recomputed_from", "") if "recomputed_value" in raw else "",
    )
    measure = next((m for m in _src.MEASURES if m["id"] == raw.get("measure_id")), None)
    if measure:
        ev.independent_test = measure.get("test", "")
    try:
        ev.fresh, ev.aim_ok = _src.freshness_and_aim(raw.get("source_id", ""))
        # How old the freshness CLAIM is, which is not how old the data is. A
        # daily check asks the publishers, but nothing writes its answer back
        # into the record, so "current" means "nothing newer written down yet".
        if ev.fresh is not None and _src.recorded_on():
            ev.notes.append(
                f"Freshness is as recorded on {_src.recorded_on()}: no newer "
                "release from this publisher had been written down.")
    except Exception:                    # noqa: BLE001 — unknown, never assumed ok
        ev.fresh, ev.aim_ok = None, None

    out = ev.to_dict()
    g = out["gate"]
    name = _title(rec.get("district_name", num))
    text = (
        f"{name} ({num}), {ev.metric}, fiscal {ev.fiscal_year}: "
        f"{_usd(ev.value)} per student.\n"
        f"Working: {ev.numerator:,} divided by {ev.denominator:,} "
        f"({ev.denominator_type}). Formula: {ev.formula}.\n"
        f"Published by {ev.source}.\n"
        f"Publication gate: {g['verdict']}. "
        + "; ".join(f"{k}={v}" for k, v in g["checks"].items()) + ".\n"
        + (" ".join(g["why"]) + "\n" if g["why"] else "")
        + (f"Caveat: {' '.join(ev.notes)}\n" if ev.notes else "")
        + ("This figure is VERIFIED: a second, independent re-read of the source "
           "data by different code produced the same number. That means two roads "
           "agree. It does NOT mean the figure is true — both roads read the same "
           "cleaned CSV, and neither can make TEA's filing right, because districts "
           "file PEIMS and it is corrected for years afterwards.\n"
           if g["verdict"] == _lin.VERIFIED else
           "This figure did NOT pass every check. Say so if you quote it.\n"))
    return text, {**out, "available_metrics": available,
                  "limits": data["meta"].get("limits", [])}


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
    absent = rec.get("absences") or []
    absent_findings = [a for a in absent if a.get("is_finding")]
    absent_context = [a for a in absent if not a.get("is_finding")]
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
        + ("\n\nWhat did NOT happen (these are findings, not missing data):\n"
           + "\n".join(f"  - {a['sentence']}" for a in absent_findings)
           if absent_findings else "")
        + ("\n\nNot shown, and why:\n"
           + "\n".join(f"  - {a['sentence']}" for a in absent_context)
           if absent_context else "")
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


def district_debt(args: dict) -> tuple[str, dict]:
    num = _resolve(args.get("district_number"))
    data = _need(_api()._debt, "debt")
    rec = data["districts"].get(num)
    if rec is None:
        raise ToolError(
            f"The Texas Bond Review Board tracks no outstanding bonded debt for "
            f"district {num}. It owes no principal and no interest on bonds — that "
            f"is a finding about the district, not missing data.")
    name = _title(rec.get("district_name", num))
    fy = data["meta"]["fiscal_year"]
    lines = [
        f"{name} ({num}) still owes {_big(rec['total'])} as of fiscal {fy}: "
        f"{_big(rec['principal'])} of principal and {_big(rec['interest'])} of "
        f"interest not yet paid ({rec['interest_share_pct']}% of the total).",
        f"That is {_usd(rec['per_student'])} per student, owed over decades rather "
        f"than in a year. On debt already sold it clears in {rec['clears_in']}.",
    ]
    cab = rec.get("cab")
    if cab:
        peak = cab.get("peak")
        lines.append(
            f"It carries capital appreciation bonds, which pay nothing until "
            f"maturity: {_big(cab['deferred_interest'])} of interest is deferred "
            f"against {_big(cab['principal_outstanding'])} of principal outstanding.")
        # The ratio only ever travels attached to the year it was taken at, so a
        # model quoting it cannot present a peak-year figure as a current one.
        lines.append(
            f"At its peak in {peak['year']} that was "
            f"{peak['repaid_per_dollar_borrowed']}x repaid per dollar borrowed on "
            f"{_big(peak['principal'])}. The ratio is quoted at the peak year and "
            f"nowhere else — on a balance being paid off it rises by itself."
            if peak else
            "No dollars-repaid-per-dollar-borrowed figure is published for it: its "
            "reported years are incomplete, so the terms it signed are not in the "
            "record. The deferred interest above is known; the ratio is not.")
    lines.append(
        "Borrowing to build schools is lawful and ordinary, and this is a balance "
        "sheet rather than a budget — it sits outside TEA's operating total "
        "entirely and is not comparable to it.")
    return "\n".join(lines), {**rec, "limits": data["meta"].get("limits", [])}


def district_campuses(args: dict) -> tuple[str, dict]:
    num = _resolve(args.get("district_number"))
    data = _need(_api()._campuses, "campus")
    rec = data["districts"].get(num)
    if rec is None:
        raise ToolError(
            f"TEA published no campus rating for district {num} in "
            f"{data['meta']['year']}. That is missing data, not a verdict on its "
            f"schools — a campus goes unrated when it has too few tested "
            f"students or is in its first year.")
    name = _title(rec.get("district_name", num))
    worst = [c for c in rec["campuses"] if c["rating"] in ("D", "F")
             and not c["is_alternative_education"]]
    lines = [
        f"{name} ({num}) is rated {rec['district_rating']} by Texas. Its "
        f"{len(rec['campuses'])} rated campuses run from {rec['worst']} to "
        f"{rec['best']}" + (f", spanning {rec['spans_grades']} letter grades."
                            if rec["spans_grades"] else ".")]
    if worst:
        lines.append(
            f"{rec['students_below_a_d']:,} of its students attend one of the "
            f"{len(worst)} campuses rated D or F:")
        lines += [f"  {c['rating']}  {_title(c['campus_name'])} "
                  f"({c['students']:,} students, {c['pct_poor']}% low-income)"
                  for c in worst[:8]]
    else:
        lines.append("No campus of its is rated D or F.")
    lines.append(
        "A district rating is an average over campuses and hides its own tails; "
        "this is the spread inside one district and is not a comparison with "
        "campuses elsewhere. Unrated campuses are excluded — that is missing "
        "data, not failure. A rating measures tested performance against state "
        "targets, not a school.")
    return "\n".join(lines), {**rec, "limits": data["meta"].get("limits", [])}


def district_national(args: dict) -> tuple[str, dict]:
    num = _resolve(args.get("district_number"))
    data = _need(_api()._national, "national")
    tx = data["states"]["texas"]
    nat = data["national"]
    fy = data["meta"]["fiscal_year"]
    rec = data["districts"].get(num)
    name = _title(_api()._district_name(num))
    # One wording per absence, owned by src/absences.py — the web endpoint
    # serves the same sentences, so a correction lands in both places.
    if rec is None:
        why = data.get("absent", {}).get(num)
        raise ToolError(absences.no_national_row(
            name, is_charter=why == "charter")["sentence"])
    if rec.get("ppcs") is None:
        # A handful of rows resolve to a TEA number but carry no usable
        # figure (the Census reports no positive spending or enrolment).
        raise ToolError(
            f"The Census fiscal {fy} file has a row for {name} ({num}) but "
            f"no usable per-pupil spending figure — it reports no positive "
            f"spending or enrolment for it. That is missing information, "
            f"not a verdict.")
    lines = [
        f"{name} ({num}) spent {_usd(rec['ppcs'])} per student in Census "
        f"current spending, fiscal {fy}."]
    if rec.get("pctile") is not None:
        lines.append(
            f"That is more per student than {rec['pctile']}% of the "
            f"{nat['districts_in_pool']:,} U.S. districts with 500+ students "
            f"(the middle one spends {_usd(nat['median_ppcs'])}).")
    else:
        lines.append(
            "It is shown but not ranked: under 500 students, per-student "
            "figures swing on a single hire — the same rule used across the "
            "site.")
    lines.append(
        f"Texas as a whole ranks {tx['rank']} of {tx['of']} ({tx['who']}) at "
        f"{_usd(tx['ppe'])} per student in average daily attendance, NPEFS "
        f"fiscal {fy}. Dividing by fall membership instead moves Texas only "
        f"to {data['states']['denominator_check']['rank_by_membership']}, so "
        f"the denominator choice is not the story.")
    lines.append(
        "Current spending is the Census's own figure and EXCLUDES "
        "construction, land and debt — it is smaller than, and never mixed "
        f"with, the TEA all-funds figures other tools here report. Fiscal "
        f"{fy} is an earlier year than the TEA data on this site; never "
        f"blend the two in one number.")
    return "\n".join(lines), {
        "district_number": num, **rec,
        "states": {"texas": tx}, "national": nat,
        "limits": data["meta"].get("limits", [])}


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
        except (ToolError, NeedsInput):
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
        "name": "district_lineage",
        "title": "Why is this number this number",
        "description": ("The working behind a published per-student revenue figure: "
                        "numerator, denominator, which student count the denominator "
                        "IS, the formula, the publisher, and the verdict of the "
                        "publication gate — whether an independent re-read of TEA's "
                        "own file agreed, whether the source is current, and whether "
                        "the source check was aimed at the file actually published "
                        "from. Call this before quoting a figure as settled. The "
                        "verdict may be UNVERIFIED, STALE or REFUSED, and those are "
                        "returned as plainly as VERIFIED."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "district_number": _DISTRICT_ARG,
                "metric": {"type": "string",
                           "enum": ["total_per_student", "local_per_student",
                                    "state_per_student", "federal_per_student"],
                           "description": "Which published figure to open up. "
                                          "Defaults to total_per_student."},
            },
            "required": ["district_number"], "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
        "handler": district_lineage,
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
        "name": "district_debt",
        "title": "What a district still owes, and the year it clears",
        "description": ("Principal and interest still outstanding as the Texas Bond "
                        "Review Board reports it — the balance, not the yearly "
                        "payment every other figure here describes. Includes the "
                        "interest share, the per-student balance, the year the debt "
                        "clears, and any capital appreciation bonds, which pay "
                        "nothing until maturity."),
        "inputSchema": {"type": "object", "properties": {"district_number": _DISTRICT_ARG},
                        "required": ["district_number"], "additionalProperties": False},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
        "handler": district_debt,
    },
    {
        "name": "district_campuses",
        "title": "The campuses inside a district, and what the district rating hides",
        "description": ("Every campus TEA rated in this district, worst first, "
                        "against the district's own A-F rating. A district "
                        "rating is an average and hides its tails: 138,664 Texas "
                        "students attend a campus rated D or F inside a district "
                        "rated A or B. Unrated campuses are excluded as missing "
                        "data, not failure."),
        "inputSchema": {"type": "object", "properties": {"district_number": _DISTRICT_ARG},
                        "required": ["district_number"], "additionalProperties": False},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
        "handler": district_campuses,
    },
    {
        "name": "district_national",
        "title": "A district against every other U.S. district",
        "description": ("The Census Bureau's own per-pupil current spending for "
                        "this district and its percentile among the U.S. "
                        "districts with 500+ students, plus where Texas ranks "
                        "among the states. The fiscal year travels in the "
                        "result — it is earlier than the TEA data here, and "
                        "current spending excludes construction and debt, so "
                        "never mix it with the all-funds figures other tools "
                        "report. Charters have no Census row anywhere in the "
                        "country, by construction."),
        "inputSchema": {"type": "object", "properties": {"district_number": _DISTRICT_ARG},
                        "required": ["district_number"], "additionalProperties": False},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
        "handler": district_national,
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


def call_tool(name: str, args: dict, input_responses: dict = None) -> dict:
    """Raises KeyError for an unknown tool — a protocol error. Anything the
    model could fix by calling differently comes back as isError instead.

    `input_responses` carries an MRTR reply (SEP-2322). When the previous call
    returned `input_required`, the client re-sends the same arguments plus the
    answer; it is merged in here so the handler never learns that a round trip
    happened.
    """
    tool = _BY_NAME[name]
    for key, reply in (input_responses or {}).items():
        if not isinstance(reply, dict):
            continue
        if reply.get("action") != "accept":
            # Declined or cancelled. Nothing was done, and saying so plainly is
            # better than proceeding with a guess — guessing between two
            # same-named districts is the failure this whole path exists for.
            return {"content": [{"type": "text", "text": (
                f"No district was chosen, so nothing was looked up. "
                f"Call {name} again with a six-digit district_number.")}],
                "isError": True}
        args = {**args, **(reply.get("content") or {})}
        del key
    try:
        text, structured = tool["handler"](args)
    except NeedsInput as e:
        # Not an error: the server is asking, and the client must come back
        # with a different JSON-RPC id per the spec.
        return {"resultType": "input_required", "inputRequests": e.as_input_request()}
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
