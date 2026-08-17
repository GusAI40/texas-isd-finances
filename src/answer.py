"""The answer contract: turn one model paragraph into a structured answer.

Why this module exists
----------------------
`/query` used to return `{"success": true, "answer": "<whatever the model
wrote>"}` and the sheet rendered that string with `textContent`. That is
correct security — a model's output must never reach `innerHTML` — but it
means every `**bold**`, `### heading` and `| table |` the model emits is
displayed as literal punctuation. The visible bug is Markdown syntax on
screen; the actual defect is that **presentation was delegated to the model**.

The fix is not a Markdown library. It is a contract:

    trusted data -> deterministic calculation -> STRUCTURED ANSWER -> UI

The model decides what the data *means*. This module decides what the answer
*is made of*. The renderer decides what it *looks like*. Each layer can be
tested on its own, and the model can never inject markup, because nothing it
writes is ever interpreted as markup — its text is parsed into typed blocks
and inline runs, and the renderer builds DOM nodes from those.

What this deliberately does NOT do
----------------------------------
It does not let the model invent structure that outranks the data. Rankings,
peers and figures come from the deterministic engines this repo already has
(`district_similarity`, the lineage layer, the committed artefacts). If the
model writes a ranking in prose, that is prose — it is never promoted into a
"ranked table" component, because a table implies a computation happened.
"""
from __future__ import annotations

import re
from typing import Any

# --- question classification ------------------------------------------------
# The point of classifying is not cleverness; it is that a fact question and a
# ranking question deserve different SHAPES, and that follow-up suggestions
# must stay inside what this product can actually answer.

KINDS = ("peer", "comparison", "ranking", "trend", "debt", "bond",
         "enrollment", "spending", "diagnostic", "fact")

_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    # "districts like" earns its place: "show me districts like Katy ISD" is the
    # most natural way a reader asks for peers and it matches none of the
    # formal words. ("like argyle" sat here as a leftover placeholder, which
    # matched exactly one district in Texas.)
    ("peer", ("comparable", "similar", "peers", "peer district",
              "districts like", "district like")),
    ("comparison", ("compare", " vs ", "versus", "against", "difference between")),
    ("ranking", ("most", "least", "highest", "lowest", "top ", "rank", "which district")),
    ("trend", ("over time", "since", "trend", "changed", "growth", "history",
               "last 5", "last five", "last 10", "last ten")),
    ("debt", ("debt", "owe", "borrow", "repayment")),
    ("bond", ("bond", "ballot", "election", "voters")),
    ("enrollment", ("enrollment", "enrolment", "students attend", "how many students")),
    # Diagnostic sits ABOVE spending deliberately: "is X spending too much" is
    # a judgement question, not a lookup, and answering it with a bare figure
    # is how a reader is left to draw the comparison themselves.
    ("diagnostic", ("too much", "overspend", "should ", "is it normal", "unusual",
                    "why ", "problem", "trouble", "at risk", "in danger",
                    "healthy", "wrong with")),
    ("spending", ("spend", "spending", "per student", "budget", "expenditure", "cost")),
]


def classify(question: str) -> str:
    """Best-effort question type. Ties break toward the more specific kind."""
    q = f" {(question or '').lower().strip()} "
    for kind, needles in _PATTERNS:
        if any(n in q for n in needles):
            return kind
    return "fact"


# --- parsing the model's prose into typed blocks -----------------------------
# Everything below converts text to DATA. No HTML is produced here, and the
# renderer never receives a string it is allowed to interpret as markup.

_BOLD = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
# Marks that carry no meaning we keep, and MUST NOT reach the reader as
# punctuation. Backticks are always markup. A single `*emphasis*` loses its
# emphasis and keeps its words. Underscores are deliberately left alone:
# `all_funds_total_disbursements` is a column name the prompt itself shows the
# model, and stripping it renders "allfundstotaldisbursements".
_STRIP = re.compile(r"`+|(?<!\*)\*(?!\*)")
_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*)$")
_BULLET = re.compile(r"^\s{0,3}[-*•]\s+(.*)$")
_NUMBERED = re.compile(r"^\s{0,3}\d+[.)]\s+(.*)$")
_TABLE_SEP = re.compile(r"^\s*\|?[\s:-]*\|[\s|:-]*$")


def runs(text: str) -> list[dict[str, Any]]:
    """Split one line into inline runs: [{"t": "...", "b": bool}].

    Bold is the only inline mark carried through. Italic and inline code were
    considered and dropped: the model reaches for them decoratively, and every
    additional mark is another thing the renderer must be trusted to escape.
    A run is plain data — the renderer makes a text node or a <b> and nothing
    else can happen.
    """
    out: list[dict[str, Any]] = []
    pos = 0
    for m in _BOLD.finditer(text):
        if m.start() > pos:
            out.append({"t": text[pos:m.start()], "b": False})
        out.append({"t": m.group(1) or m.group(2) or "", "b": True})
        pos = m.end()
    if pos < len(text):
        out.append({"t": text[pos:], "b": False})
    out = [{"t": _STRIP.sub("", r["t"]), "b": r["b"]} for r in out]
    return [r for r in out if r["t"]] or [{"t": _STRIP.sub("", text), "b": False}]


def plain(rs: list[dict[str, Any]]) -> str:
    """The text of a run list, with nothing added and nothing marked up."""
    return "".join(r["t"] for r in rs).strip()


def _table_row(line: str) -> list[str]:
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    return cells


def blocks(text: str) -> list[dict[str, Any]]:
    """Parse model prose into typed blocks the renderer can draw.

    Block kinds: heading, paragraph, list, table. Anything unrecognised stays
    a paragraph — an unknown line must still reach the reader, just without
    special treatment.
    """
    lines = (text or "").replace("\r\n", "\n").split("\n")
    out: list[dict[str, Any]] = []
    para: list[str] = []
    items: list[str] = []
    table: list[list[str]] = []

    def flush_para() -> None:
        if para:
            out.append({"type": "paragraph", "runs": runs(" ".join(para).strip())})
            para.clear()

    def flush_list() -> None:
        if items:
            out.append({"type": "list", "items": [runs(i) for i in items]})
            items.clear()

    def flush_table() -> None:
        if table:
            head, *body = table
            # A one-row "table" is a fragment, not a table — keep it readable
            # rather than drawing a header with nothing under it.
            if body:
                out.append({"type": "table", "head": head, "rows": body})
            else:
                out.append({"type": "paragraph", "runs": runs(" ".join(head))})
            table.clear()

    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            flush_para()
            flush_list()
            flush_table()
            continue
        if line.lstrip().startswith("|") and line.count("|") >= 2:
            if _TABLE_SEP.match(line):        # the |---|---| divider
                continue
            flush_para()
            flush_list()
            table.append(_table_row(line))
            continue
        flush_table()
        m = _HEADING.match(line)
        if m:
            flush_para()
            flush_list()
            out.append({"type": "heading", "text": m.group(2).strip()})
            continue
        m = _BULLET.match(line) or _NUMBERED.match(line)
        if m:
            flush_para()
            items.append(m.group(1).strip())
            continue
        flush_list()
        para.append(line.strip())

    flush_para()
    flush_list()
    flush_table()
    return out


def take_lead(bs: list[dict[str, Any]]) -> tuple[list[dict[str, Any]] | None,
                                                 list[dict[str, Any]]]:
    """Split the opening paragraph off as the lead. Returns (lead_runs, rest).

    The lead is the model's WHOLE first paragraph, promoted to the top of the
    card, and it is then removed from the blocks. Nothing is summarised and
    nothing is dropped.

    An earlier version took only the first sentence or two and asked the
    renderer to skip block 0 if the two shared their first 40 characters. They
    always did — so on the most likely answer shape, a single paragraph of
    three or four sentences, everything after sentence two was DELETED from the
    screen while the screen-reader announcement (built from the blocks) still
    read it. Sighted and screen-reader users got different answers to the same
    question. Promoting the whole paragraph makes the duplication impossible
    rather than detected.

    If the answer does not open with a paragraph — it starts with a table or a
    heading — there is NO lead. Slicing the first chunk of raw text off such an
    answer put `| District | Per student |` into the biggest type on the card,
    which is the exact defect this module exists to remove.
    """
    if bs and bs[0].get("type") == "paragraph":
        return bs[0]["runs"], bs[1:]
    return None, bs


# --- follow-ups: only questions this product can actually answer --------------
# The rule that matters: a suggestion the system cannot answer is worse than no
# suggestion, because it advertises a capability and then fails. These are
# generated from the question KIND and the district in context, and every one
# maps to data this repo publishes (spending, debt, bonds, peers, trends,
# campuses, outcomes). Nothing here is invented by the model.

def _fill(templates: list[tuple[str, str]], name: str | None) -> list[dict[str, str]]:
    who = name or "this district"
    return [{"label": label, "question": q.replace("{d}", who)}
            for label, q in templates]


_FOLLOW_UPS: dict[str, list[tuple[str, str]]] = {
    "peer": [
        ("Why that match?", "Why is that district the closest comparison to {d}?"),
        ("Spending side by side",
         "How does spending per student compare between {d} and its closest peer?"),
        ("Debt per student", "How does {d}'s debt per student compare with its peer districts?"),
        ("Beats expectations?", "Does {d} do better or worse than its student need predicts?"),
    ],
    "comparison": [
        ("Who spends more", "Which of those districts spends more per student, and on what?"),
        ("Debt comparison", "How does debt per student compare between them?"),
        ("Outcomes", "How do their STAAR results compare at the Meets standard?"),
        ("Over time", "How have those districts' budgets changed since 2009?"),
    ],
    "ranking": [
        ("Why the leader?", "Why does the top district in that list spend the most?"),
        ("Fair comparison", "Are those districts comparable in size and student need?"),
        ("Statewide context", "What is the statewide median for that measure?"),
    ],
    "trend": [
        ("What drove it", "Which spending categories drove that change?"),
        ("Inflation-adjusted", "Is that change still there in constant 2024 dollars?"),
        ("Versus the state", "How does that trend compare with the statewide line?"),
        ("Debt's part", "How much of the change is debt service rather than operations?"),
    ],
    "debt": [
        ("Per student", "What is {d}'s debt per student?"),
        ("What voters approved", "Which bond elections created {d}'s debt?"),
        ("When it clears", "When does {d}'s existing debt finish being repaid?"),
        ("Peer comparison", "How does {d}'s debt compare with similar districts?"),
    ],
    "bond": [
        ("What it funded", "What did {d}'s bond propositions say the money was for?"),
        ("Debt today", "How much does {d} still owe on its bonds?"),
        ("Tax effect", "What is the school tax on a $300,000 home in {d}?"),
        ("Did results move?", "Did {d}'s results change after its bond passed?"),
    ],
    "enrollment": [
        ("Money per student", "How much does {d} spend per student?"),
        ("Enrollment trend", "How has {d}'s enrollment changed since 2009?"),
        ("Who it serves", "What share of {d}'s students are economically disadvantaged?"),
        ("Comparable districts", "Which districts are most comparable to {d}?"),
    ],
    "spending": [
        ("Where it goes", "How does {d} split spending between teaching, buildings and debt?"),
        ("Versus peers", "Do comparable districts spend more or less than {d} per student?"),
        ("Who pays", "How much of {d}'s money is local, state and federal?"),
        ("What it bought", "Do {d}'s results beat what its student need predicts?"),
    ],
    "diagnostic": [
        ("Compare fairly", "Which districts are most comparable to {d}?"),
        ("Break it down", "Which categories explain {d}'s spending level?"),
        ("Operating vs capital", "How much of {d}'s spending is construction and debt?"),
        ("Outcome check", "Does {d} do better than its student need predicts?"),
    ],
    "fact": [
        ("Spending per student", "How much does {d} spend per student?"),
        ("Comparable districts", "Which districts are most comparable to {d}?"),
        ("Debt", "How much debt does {d} carry?"),
        ("Over time", "How has {d} changed since 2009?"),
    ],
}


def follow_ups(kind: str, district_name: str | None, asked: str) -> list[dict[str, str]]:
    """3–4 next questions, specific and answerable.

    The label stays short so a chip reads cleanly; the `question` carries the
    full context so the engine receives something precise. Anything too close
    to what was just asked is dropped — repeating the reader's own question
    back at them is the classic empty suggestion.
    """
    picked = _fill(_FOLLOW_UPS.get(kind, _FOLLOW_UPS["fact"]), district_name)
    seen = re.sub(r"[^a-z ]", "", (asked or "").lower())
    seen_words = {w for w in seen.split() if len(w) > 4}
    out = []
    for f in picked:
        words = {w for w in re.sub(r"[^a-z ]", "", f["question"].lower()).split()
                 if len(w) > 4}
        overlap = len(words & seen_words) / max(len(words), 1)
        if overlap < 0.55:            # near-duplicate of what they just asked
            out.append(f)
    return (out or picked)[:4]


# --- the contract ------------------------------------------------------------

SOURCES = [
    {"name": "Texas Education Agency — Summarized PEIMS financial data",
     "url": "https://tea.texas.gov/about-tea/state-funding/state-funding-reports-"
            "and-data/peims-financial-data-downloads"},
    {"name": "Every figure on this site, with its working", "url": "/sources"},
]

LIMITS = [
    "Answers are generated by an AI reading a read-only copy of the state's own "
    "figures. It can misread a question — check anything important against the "
    "district page, where each number opens its own calculation.",
]


# --- deterministic attachments ------------------------------------------------
# Everything above is the MODEL's answer, reshaped. Everything below is OURS:
# figures and rankings read straight out of the committed artefacts, computed by
# the build pipeline and checked by the lineage gate. The model may explain
# them. It does not produce them, and it cannot change them.

def _economics() -> dict[str, Any] | None:
    """The committed economics artefact, or None if this deployment lacks it.

    Imported at call time for the same reason src/mcp_tools.py does it: api.py
    imports this module, so a module-level import would be a cycle.
    """
    try:
        from . import api
        return api._economics()
    except Exception:                    # noqa: BLE001 — an attachment is optional
        return None


# label, artefact key, and the lineage metric that opens its working. `None`
# means the figure has no division behind it: `students` is a count, and
# `total_per_student` is operating + debt COMPOSED — the house rule is that a
# composed total never gets division lineage, because there is no such division.
_FIGURE_SPEC: list[tuple[str, str, str | None]] = [
    ("Students", "students", None),
    ("Operating per student", "operating_per_student", "spend_operating_per_student"),
    ("Instruction per student", "instruction_per_student", "spend_instruction_per_student"),
    ("Debt service per student", "debt_per_student", "spend_debt_per_student"),
]


def _money(v: Any) -> str:
    return f"${int(round(float(v))):,}"


def figures(district_number: str | None) -> dict[str, Any] | None:
    """The district's headline numbers, from the artefact — never from prose.

    Deliberately NOT parsed out of what the model wrote. A figure lifted from
    prose is only as right as the sentence it came from; these are the same
    values the district page publishes, each carrying the metric key that opens
    its own calculation.
    """
    data = _economics()
    if not data or not district_number:
        return None
    rec = (data.get("districts") or {}).get(district_number)
    if not rec:
        return None
    alloc = rec.get("allocation") or {}
    cards = []
    for label, key, metric in _FIGURE_SPEC:
        value = rec.get(key) if key == "students" else alloc.get(key)
        if value in (None, ""):
            continue
        cards.append({
            "label": label,
            "value": f"{int(value):,}" if key == "students" else _money(value),
            "metric": metric,
        })
    if not cards:
        return None
    return {
        "year": rec.get("year"),
        "district_number": district_number,
        "name": rec.get("district_name"),
        "cards": cards,
        # The basis has to be stated or these cards look like they contradict
        # the answer above them. The model reads the finance VIEW, whose
        # per-student figure is all funds — construction included. These come
        # from the economics artefact, which reports operating and debt
        # separately and counts no construction. Both are right; they are
        # answers to different questions, and a reader deserves to be told
        # that rather than left to reconcile two numbers on one screen.
        "note": ("From the district's own filing. Operating and debt are "
                 "reported separately here, and neither counts construction — "
                 "a total that does will be larger. Click a figure for its "
                 "calculation."),
    }


_SUFFIX = re.compile(r"\b(independent school district|isd|cisd|msd|school district)\b")


def _core(name: str) -> str:
    """A district name reduced to the part a reader actually types."""
    s = _SUFFIX.sub(" ", (name or "").lower())
    return re.sub(r"[^a-z0-9 ]", " ", s).strip()


_NAME_INDEX: dict[str, str] | None = None


def _names() -> dict[str, str]:
    """core name -> district number, for every district in the artefact."""
    global _NAME_INDEX
    if _NAME_INDEX is None:
        data = _economics() or {}
        _NAME_INDEX = {}
        for num, rec in (data.get("districts") or {}).items():
            core = _core(rec.get("district_name", ""))
            if len(core) >= 4:                 # "Ore City" yes, "Ax" no
                _NAME_INDEX.setdefault(core, num)
    return _NAME_INDEX


def context_for(text: str, district_number: str | None) -> str | None:
    """Which district is this answer actually about?

    `district_number` is the page's own URL, not the question, so it is context
    and nothing more. Attaching it blindly put four large figures and a ranked
    table under a headline about someone else: a reader on a Dallas page asking
    about Argyle got Argyle's sentence over Dallas's evidence.

    Whichever districts the question and the answer NAME decide it:
      * exactly one named        -> that district, even if the URL says another
      * none named               -> the URL's district; "how much do we spend
                                    per student" on a district page is about
                                    that district
      * more than one named      -> refuse. A comparison or a ranking has no
                                    single subject, and picking one would put a
                                    ranked table under a statewide question.
    """
    named = set()
    hay = f" {_core(text)} "
    for core, num in _names().items():
        if f" {core} " in hay:
            named.add(num)
    if len(named) == 1:
        return named.pop()
    if named:
        return None
    return district_number if (_economics() or {}).get(
        "districts", {}).get(district_number) else None


def comparison(kind: str, district_number: str | None) -> dict[str, Any] | None:
    """A ranked comparison this system computed, for questions that ask for one.

    The ranking comes from `who_does_better` in the economics artefact:
    districts MATCHED on enrolment and the share of economically disadvantaged
    students, ranked by how far their results beat what those traits predict.
    That match is a build-time computation with a test behind it. The model is
    never asked to rank anything — if it writes a ranking in prose it stays
    prose, because a table implies a computation happened.
    """
    # `ranking` is deliberately absent. "Which district spends the most in
    # Texas" is a statewide question, and heading the reader's own peers with
    # "comparable districts getting better results" answers a question nobody
    # asked.
    if kind not in ("peer", "comparison", "diagnostic", "spending"):
        return None
    data = _economics()
    if not data or not district_number:
        return None
    rec = (data.get("districts") or {}).get(district_number)
    if not rec:
        return None
    rows = rec.get("who_does_better") or []
    if not rows:
        return None
    own = rec.get("own") or {}
    return {
        "title": "Comparable districts getting better results",
        "basis": ("Matched on enrolment and the share of students who are "
                  "economically disadvantaged, then ranked by how far results "
                  "beat what those two traits predict. Computed from the "
                  "state's filings — not written by the AI."),
        "head": ["District", "Students", "Low-income", "Beats prediction by"],
        "rows": [[r.get("name", ""), f"{int(r.get('students') or 0):,}",
                  f"{r.get('pct_poor')}%", f"+{r.get('beats_by')} pts"]
                 for r in rows[:5]],
        "self": ({"name": rec.get("district_name"),
                  "students": f"{int(rec.get('students') or 0):,}",
                  "pct_poor": f"{own.get('pct_poor')}%"} if own.get("pct_poor") else None),
    }


def build(question: str, answer_text: str, *,
          district_number: str | None = None) -> dict[str, Any]:
    """The structured answer the API returns and the sheet renders.

    The district NAME is never accepted from the caller — it is resolved from
    the artefact for the number the page is showing, so a client cannot label
    an answer with a district it is not displaying.
    """
    kind = classify(question)
    ctx = context_for(f"{question} {answer_text}", district_number)
    facts = figures(ctx)
    district_name = facts.get("name") if facts else None
    lead_runs, rest = take_lead(blocks(answer_text))
    return {
        "kind": kind,
        "lead": plain(lead_runs) if lead_runs else "",
        "lead_runs": lead_runs,
        "blocks": rest,
        "district": {"name": district_name, "number": ctx} if ctx else None,
        "figures": facts,
        "comparison": comparison(kind, ctx),
        "sources": SOURCES,
        "limitations": LIMITS,
        "follow_ups": follow_ups(kind, district_name, question),
    }
