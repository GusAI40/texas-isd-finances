"""The intelligence layer: what the event stream means.

This turns the rows written by src/tracking.py and the chat endpoint into the
answers a person actually asks — who is engaging, with what, what they are
trying to understand, and what to fix next. It owns no storage: every figure
here is a query over `visitor_event`, `chat_turn` and `outreach_recipient`,
which is what keeps one journey from having two versions.

WHO IS IN THESE NUMBERS
-----------------------
Only people we emailed. The site's published promise is that it measures the
site and not the visitor, with that one stated exception, and this module does
not widen it: every behavioural figure below comes from rows that exist only
for a visitor carrying a token we minted and mailed.

That makes the denominator small and it must be stated everywhere rather than
implied. Wave 1 (571 sends, 2026-08-11/12/13) predates journey tracking and
CANNOT be retrofitted — its links are already delivered. The tracked population
is wave 2 onward. A dashboard that says "12 visitors" without saying "of 100
tracked, out of 671 mailed" invites a conclusion about Texas superintendents
from a sample that is really a conclusion about one send.

WHAT THIS DELIBERATELY DOES NOT DO
----------------------------------
No regression, no modelling, no "predicted" anything. The spec that asked for
this layer put regression at the end on purpose, and at the current sample size
— roughly a hundred tracked recipients and a single-digit number of replies —
a logistic model would produce confident-looking coefficients with confidence
intervals spanning the whole plausible range. `power()` below reports what the
data can and cannot support, and the dashboard prints its refusal. When the
sample grows the refusal lifts itself.
"""
from __future__ import annotations

from typing import Any

# --- the engagement score ---------------------------------------------------
# Deterministic, documented, and shown factor by factor wherever it appears.
# It is an ENGAGEMENT score, never a prediction: nothing here has been fitted
# against an outcome, and calling it "intent" or "likelihood" would claim a
# validation nobody has done. The weights are a stated editorial judgement
# about which behaviours are harder to produce by accident — a scanner can
# fetch a link, but it does not come back nine days later and read for a
# minute — and they are published so a reader can disagree with them.

WEIGHTS: list[tuple[str, str, int]] = [
    ("clicked",        "Clicked the email",                        10),
    ("returned",       "Came back on their own, later",            20),
    ("multi_session",  "More than one visit",                      10),
    ("deep_read",      "Read a page for 60 seconds or more",       10),
    ("section_depth",  "Engaged 3+ sections of a report",          15),
    ("asked",          "Asked the assistant a question",           20),
    ("asked_three",    "Asked three or more questions",            15),
    ("downloaded",     "Downloaded a chart or the data",           10),
    ("replied",        "Replied to the email",                     40),
]
MAX_SCORE = sum(w for _, _, w in WEIGHTS)


def score(facts: dict[str, Any]) -> dict[str, Any]:
    """Score one recipient from their own counted behaviour.

    Returns the total AND every factor with whether it fired, because a score
    a reader cannot take apart is a number they have to trust instead of
    check — and this project's whole argument is the opposite.
    """
    got = []
    total = 0
    for key, label, weight in WEIGHTS:
        fired = bool(facts.get(key))
        if fired:
            total += weight
        got.append({"key": key, "label": label, "weight": weight, "fired": fired})
    return {"score": total, "max": MAX_SCORE, "factors": got,
            "band": band(total)}


def band(total: int) -> str:
    """Three bands, named for what they describe rather than for a sales stage.

    'Hot lead' would assert an intention nobody stated; these say what the
    person did.
    """
    if total >= 70:
        return "deeply engaged"
    if total >= 35:
        return "actively reading"
    if total > 0:
        return "arrived"
    return "no recorded activity"


def facts_from_row(r: dict[str, Any]) -> dict[str, Any]:
    """Turn one aggregate row into the boolean facts the score consumes."""
    return {
        "clicked":       bool(r.get("first_click_at")),
        "returned":      int(r.get("returns") or 0) > 0,
        "multi_session": int(r.get("sessions") or 0) > 1,
        "deep_read":     int(r.get("max_dwell_ms") or 0) >= 60_000,
        "section_depth": int(r.get("distinct_sections") or 0) >= 3,
        "asked":         int(r.get("questions") or 0) > 0,
        "asked_three":   int(r.get("questions") or 0) >= 3,
        "downloaded":    int(r.get("downloads") or 0) > 0,
        "replied":       bool(r.get("replied_at")),
    }


# --- the funnel -------------------------------------------------------------
# One conversion, three signals. A reply is the only real outcome this product
# has; return visits, downloads and deep chat engagement are intent signals.
# Promoting them to conversions would manufacture a funnel with four exits
# where one exists, which is how a dashboard starts flattering its owner.

FUNNEL_STAGES = [
    ("sent",       "Emailed"),
    ("opened",     "Opened (unreliable — see note)"),
    ("clicked",    "Clicked through"),
    ("engaged",    "Read something properly"),
    ("asked",      "Asked the assistant"),
    ("replied",    "Replied — the conversion"),
]

# Two populations live on this dashboard and they are NOT the same set. The
# funnel, the people table and the accounts are recipients we emailed. The
# question panels are EVERY visitor, because an anonymous question is still a
# Texan telling us what their district's page failed to explain — that is the
# most useful signal here and throwing it away to keep one denominator would be
# a worse answer. Mixing them silently would not: caught when the dashboard
# showed 1 person and 2 conversations, which reads as a bug until you know why.
POPULATION_RECIPIENTS = "people we emailed and can track"
POPULATION_EVERYONE = "every visitor, including anonymous ones"

OPEN_CAVEAT = ("Opens are a pixel load. Mail-security appliances fetch it with "
               "no human present and privacy features block it entirely, so "
               "this number is wrong in both directions with no way to bound "
               "the error. It is shown because hiding it invites someone to "
               "compute it themselves; it is never a rate to quote.")


# --- SQL --------------------------------------------------------------------
# Kept here rather than in api.py so the shapes can be read in one place, and
# so a test can assert what each one counts.

PEOPLE_SQL = """
SELECT r.rid, r.email, r.district_number, r.campaign, r.sent_at,
       j.first_open_at, j.first_click_at, j.pageviews, j.sessions,
       j.distinct_pages, j.total_dwell_ms, j.last_seen_at,
       coalesce(x.returns, 0)            AS returns,
       coalesce(x.questions, 0)          AS questions,
       coalesce(x.downloads, 0)          AS downloads,
       coalesce(x.distinct_sections, 0)  AS distinct_sections,
       coalesce(x.max_dwell_ms, 0)       AS max_dwell_ms,
       x.replied_at
FROM public.outreach_recipient r
JOIN public.v_recipient_journey j ON j.rid = r.rid
LEFT JOIN (
    SELECT rid,
           count(*) FILTER (WHERE event = 'return')   AS returns,
           count(*) FILTER (WHERE event = 'question') AS questions,
           count(*) FILTER (WHERE event = 'download') AS downloads,
           count(DISTINCT section) FILTER (WHERE event = 'section') AS distinct_sections,
           max(dwell_ms) FILTER (WHERE event = 'dwell') AS max_dwell_ms,
           min(occurred_at) FILTER (WHERE event = 'reply') AS replied_at
    FROM public.visitor_event
    GROUP BY rid
) x ON x.rid = r.rid
"""

TIMELINE_SQL = """
SELECT e.occurred_at, e.event, e.path, e.section, e.detail,
       e.district_number, e.dwell_ms, e.conversation_id
FROM public.visitor_event e
WHERE e.rid = $1
ORDER BY e.occurred_at
LIMIT 500
"""

TOP_SECTIONS_SQL = """
SELECT section,
       count(DISTINCT rid)        AS people,
       count(*)                   AS views,
       coalesce(sum(dwell_ms), 0) AS total_dwell_ms,
       round(avg(dwell_ms))       AS avg_dwell_ms
FROM public.visitor_event
WHERE event = 'section' AND section IS NOT NULL
  AND occurred_at > now() - ($1::int * interval '1 day')
GROUP BY section
ORDER BY count(DISTINCT rid) DESC, coalesce(sum(dwell_ms), 0) DESC
LIMIT 20
"""

TOP_QUESTIONS_SQL = """
SELECT kind, count(*) AS asked,
       count(*) FILTER (WHERE NOT ok) AS failed,
       round(avg(ms))                 AS avg_ms
FROM public.chat_turn
WHERE asked_at > now() - ($1::int * interval '1 day')
GROUP BY kind
ORDER BY count(*) DESC
"""

RECENT_QUESTIONS_SQL = """
SELECT conversation_id, turn, asked_at, question, kind, district_number,
       ok, ms, followup_label
FROM public.chat_turn
WHERE asked_at > now() - ($1::int * interval '1 day')
ORDER BY asked_at DESC
LIMIT 60
"""

ANSWER_QUALITY_SQL = """
SELECT count(*)                                        AS turns,
       count(DISTINCT conversation_id)                 AS conversations,
       count(*) FILTER (WHERE NOT ok)                  AS failures,
       count(*) FILTER (WHERE followup_label IS NOT NULL) AS from_followup,
       count(*) FILTER (WHERE structured)              AS structured,
       round(avg(ms))                                  AS avg_ms,
       percentile_cont(0.95) WITHIN GROUP (ORDER BY ms) AS p95_ms
FROM public.chat_turn
WHERE asked_at > now() - ($1::int * interval '1 day')
"""

ACTIVITY_SQL = """
SELECT e.occurred_at, e.event, e.path, e.section, e.detail,
       e.district_number, e.dwell_ms, r.district_number AS home_district
FROM public.visitor_event e
JOIN public.outreach_recipient r ON r.rid = e.rid
WHERE e.occurred_at > now() - ($1::int * interval '1 day')
ORDER BY e.occurred_at DESC
LIMIT 40
"""


# --- what the data can and cannot support -----------------------------------

def power(people: int, conversions: int) -> dict[str, Any]:
    """Say plainly whether these numbers can carry a statistical claim.

    The rule of thumb this uses is the usual events-per-variable one: a
    logistic model wants on the order of ten outcome events per predictor. With
    a handful of replies there is no honest model with even one predictor in
    it, and the right output is a refusal rather than a coefficient.
    """
    per_variable = 10
    supportable = conversions // per_variable
    if supportable < 1:
        verdict = "REFUSED"
        why = (f"{conversions} conversion(s) across {people} tracked people. A "
               f"model needs about {per_variable} outcome events per predictor, "
               f"so this supports no predictors at all. Any coefficient shown "
               f"here would be noise with a confidence interval wide enough to "
               f"contain both directions.")
    elif supportable < 3:
        verdict = "THIN"
        why = (f"{conversions} conversions support about {supportable} "
               f"predictor(s). Report the raw rates; treat any model as a "
               f"hypothesis to test on a later wave, not a finding.")
    else:
        verdict = "OK"
        why = (f"{conversions} conversions support roughly {supportable} "
               f"predictors at {per_variable} events each.")
    return {"verdict": verdict, "why": why, "people": people,
            "conversions": conversions, "supportable_predictors": supportable}


# --- improvement opportunities ----------------------------------------------

def opportunities(question_kinds: list[dict[str, Any]],
                  sections: list[dict[str, Any]],
                  quality: dict[str, Any]) -> list[dict[str, Any]]:
    """What to fix next, each with the evidence that produced it.

    Every item is a counted fact against a stated threshold — no model, no LLM
    intuition. An empty list is a real answer and is rendered as one: inventing
    an opportunity to fill a panel is how a dashboard trains its reader to stop
    believing it.
    """
    out: list[dict[str, Any]] = []

    failures = int(quality.get("failures") or 0)
    turns = int(quality.get("turns") or 0)
    if turns >= 20 and failures / max(turns, 1) > 0.05:
        out.append({
            "priority": "high",
            "finding": f"{failures} of {turns} questions failed to answer.",
            "evidence": "chat_turn.ok = false",
            "recommendation": "Read the failing questions below and fix the "
                              "engine or the prompt before sending another wave.",
        })

    # A topic asked often is a topic the page is not answering on its own.
    for k in question_kinds[:3]:
        asked = int(k.get("asked") or 0)
        if asked >= 10:
            out.append({
                "priority": "medium",
                "finding": f"{asked} questions were about {k.get('kind')}.",
                "evidence": "chat_turn.kind, classified deterministically by "
                            "src/answer.py",
                "recommendation": f"People are asking the assistant for "
                                  f"{k.get('kind')} rather than reading it. "
                                  f"Put that figure on the page itself.",
            })

    # A section people open and leave is a section that is not landing.
    for s in sections:
        people = int(s.get("people") or 0)
        avg = int(s.get("avg_dwell_ms") or 0)
        if people >= 5 and avg and avg < 8000:
            out.append({
                "priority": "medium",
                "finding": f"{people} people opened “{s.get('section')}” and "
                           f"stayed a median of {avg // 1000}s.",
                "evidence": "visitor_event section dwell",
                "recommendation": "Either the section answers its question in "
                                  "one glance — which is fine — or it is not "
                                  "landing. Check which by reading the "
                                  "questions asked in the same sessions.",
            })

    return out[:8]


# --- lineage ----------------------------------------------------------------
# Every headline on the dashboard states where it came from, in the same shape
# the public site uses for its financial figures. A metric nobody can trace is
# a metric nobody can correct.

LINEAGE: dict[str, str] = {
    "people": "outreach_recipient — one row per mailed token, written at send",
    "clicked": "visitor_event event='click' — the ?rid= token arriving on the site",
    "opened": "visitor_event event='email_open' — /px/{rid}.gif fetched (unreliable)",
    "sessions": "v_recipient_journey.sessions — distinct session_id per recipient",
    "sections": "visitor_event event='section' — IntersectionObserver, 4s minimum",
    "questions": "chat_turn — one row per question asked of /query",
    "conversations": "chat_turn grouped by conversation_id",
    "replied": "visitor_event event='reply' — written by the mailbox reader",
    "score": "src/intel.py WEIGHTS, applied to counted behaviour",
}
