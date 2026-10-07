"""A correct number in the wrong frame is still a lie. These tests audit frames.

Everything else in this suite proves numbers DERIVE correctly from the state's
files. None of it could catch the bug a reader found on Argyle ISD's card:
every figure was perfectly derived, and the card said "Deficit — revenue
$63.9M vs spending $193.8M" about a district whose operations ran a $532k
surplus. The $130M gap was voter-approved school construction. Operating
revenue had been compared against ALL money out the door, and by that frame
571 districts — 48% of Texas — were branded with deficits they did not have.

Derivation tests cannot see this, because the frame is chosen in the
presentation layer. So these tests read the presentation layer and assert the
framing rules directly:

  1. An operating balance compares operating with operating, never operating
     with all-funds.
  2. Any all-funds figure shown per student names what it includes wherever
     construction and debt are a material share.
  3. A change flag on all-funds spending says what usually causes one — a bond
     construction cycle — instead of presenting itself as a bare red mark.
  4. The word "Deficit" never renders from a mixed-frame comparison.

They are deliberately string-level assertions on the shipped HTML/SQL: crude,
but the failure mode is a sentence, so the test has to read sentences.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

INDEX = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
SQL = (ROOT / "sql" / "create_tables.sql").read_text(encoding="utf-8")


def _renderer_source(name):
    start = INDEX.index(f"function {name}")
    end = INDEX.find("\nfunction ", start + 1)
    return INDEX[start:] if end == -1 else INDEX[start:end]


def _render(functions, call, payload):
    """Run the shipped renderers in a bounded DOM stub, then return their output."""
    script = r"""
const fs = require('fs'), vm = require('vm');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const elements = {};
for (const id of ['hero-kpis', 'picker-title', 'hero-sub', 'hero-why', 'kpis', 'tx-pennies', 'tx-cap']) {
  elements[id] = { innerHTML: '', textContent: '', hidden: false, style: {}, dataset: {} };
}
const context = {
  state: input.payload.state || {},
  $: id => elements[id] || (elements[id] = { innerHTML: '', textContent: '', hidden: false, style: {}, dataset: {} }),
  titleCase: value => value,
  fmtMoney: value => '$' + Math.round(Number(value)).toLocaleString('en-US'),
  fmtBig: value => '$' + Math.round(Number(value)).toLocaleString('en-US'),
  fmtNum: value => Number(value).toLocaleString('en-US'),
  xb: () => '',
  ordSuf: () => 'th',
  latestOf: rows => [rows && rows.length ? rows[rows.length - 1] : null, null],
  consecutiveEnrollmentDeclines: () => 0,
  opsPerStudentNote: () => '',
  balanceCard: () => '',
  applyVisualLedger: () => {},
  dollarParts: () => input.payload.dollar,
  liveStatus: { hidden: false, textContent: '' },
  console,
};
vm.createContext(context);
for (const source of input.functions) vm.runInContext(source, context);
const value = vm.runInContext(input.call, context);
process.stdout.write(JSON.stringify({ elements, value }));
"""
    completed = subprocess.run(
        ["node", "-e", script],
        input=json.dumps({"functions": functions, "call": call, "payload": payload}),
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(completed.stdout)["elements"]


# --- the view carries both frames, so the page can compare like with like ----

def test_the_summary_view_exposes_operating_spend():
    """Without this column the page physically cannot draw an operating
    balance, and the only comparison available is the misleading one."""
    assert re.search(r"all_funds_total_operating_expenditures_by_obj\s+AS\s+operating_spend",
                     SQL), "v_finance_summary no longer exposes operating_spend"


# --- rule 1: operating vs operating ------------------------------------------

def test_the_balance_card_compares_operating_with_operating():
    assert "function balanceCard" in INDEX
    body = INDEX.split("function balanceCard", 1)[1].split("\nfunction ", 1)[0]
    assert "operating_spend" in body, "the balance card no longer uses operating spend"
    assert "Operating balance" in body


def test_the_old_mixed_frame_deficit_sentence_is_gone():
    """The exact sentence a reader disproved: operating revenue labelled
    'Revenue' against total disbursements labelled 'spending', concluding
    'Deficit'. If this reappears, 571 districts get their false deficits back."""
    assert not re.search(
        r"total_revenue\s*>=\s*cur\.total_spend\s*\?\s*'Surplus'\s*:\s*'Deficit'",
        INDEX), "the mixed-frame Surplus/Deficit comparison is back"


def test_deficit_is_never_concluded_from_total_spend():
    """'Deficit' may only ever be computed against operating_spend, and the
    fallback path (column missing) must not use the word at all.

    Checked with a 400-character window around each occurrence rather than the
    single line: the ternary that decides Surplus/Deficit and the comparison
    that justifies it are legitimately on different lines, and the first
    version of this test failed its own correct code for that reason.
    """
    for m in re.finditer(r"'Deficit'", INDEX):
        window = INDEX[max(0, m.start() - 400):m.start()]
        assert "operating_spend" in window, (
            f"'Deficit' concluded without an operating frame near: "
            f"{INDEX[m.start() - 80:m.start() + 40]!r}")


# --- rule 2: all-funds per-student figures name what they include -------------

def test_the_spend_card_names_the_operating_figure():
    assert "function opsPerStudentNote" in INDEX
    body = INDEX.split("function opsPerStudentNote", 1)[1].split("\nfunction ", 1)[0]
    assert "construction" in body and "operations run" in body


def test_the_statewide_rank_names_its_frame():
    output = _render(
        [_renderer_source("renderKPIs")],
        "renderKPIs()",
        {
            "state": {
                "summary": [{"year": 2025, "spend_per_student": 23_746, "enrollment": 139_776}],
                "peers": {"statewide": {"spend_percentile": 81, "statewide_median_spend": 17_095}},
            }
        },
    )["kpis"]["innerHTML"].lower()
    assert "all funds" in output
    assert "construction" in output
    assert "debt" in output
    with pytest.raises(AssertionError):
        assert "construction" in output.replace("construction", "")
    with pytest.raises(AssertionError):
        assert "debt" in output.replace("debt", "")


def test_the_reporter_lens_gives_both_frames():
    """The lens written for people who publish. It must never hand a reporter
    the all-funds figure without the operating figure beside it."""
    press = INDEX.split("case 'press':", 1)[1].split("default:", 1)[0]
    assert "all funds" in press
    assert "operating" in press
    assert "construction" in press


# --- rule 3: a change flag explains its usual cause ---------------------------

def test_the_spend_spike_flag_mentions_construction():
    flag = re.search(r"spend_spike_flag:\s*\[[^\]]+", INDEX)
    assert flag, "spend spike flag copy not found"
    assert "construction" in flag.group(0), (
        "an all-funds spike flag must say it is usually a bond construction "
        "year, or every growing district reads as a scandal")
    assert "All-funds" in flag.group(0)


def test_flags_are_not_called_anomalies_in_the_press_lens():
    press = INDEX.split("case 'press':", 1)[1].split("default:", 1)[0]
    assert "anomaly flags" not in press, (
        "the press lens hands 'anomaly' straight to a headline; call them "
        "change flags and say what causes them")
    assert "not an accusation" in press


# --- the blast radius stays documented ---------------------------------------

def test_the_view_comment_records_why_operating_spend_exists():
    """The comment in the SQL is the institutional memory: remove the column
    and the next maintainer re-creates the bug with no idea it ever happened."""
    idx = SQL.find("AS operating_spend")
    assert idx > -1
    context = SQL[max(0, idx - 700):idx]
    assert "Argyle" in context, "the worked example was removed from the view comment"


def test_the_deep_link_hero_does_not_lead_with_an_unqualified_all_funds_figure():
    """The headline a shared link opens on. It said "spends $31,704 per
    student" about Argyle with no qualifier — the exact sentence the forensic
    audit corrected on the cards below it."""
    public = json.loads(
        (ROOT / "tests" / "browser" / "fixtures" / "public-endpoints.json").read_text(encoding="utf-8")
    )
    dallas = public["payloads"]["dallas_summary"][-1]
    argyle = json.loads(
        (ROOT / "docs" / "evidence" / "mcp" / "framing-argyle-public.json").read_text(encoding="utf-8")
    )["row"]

    for row in (dallas, argyle):
        name = row["district_name"]
        output = _render(
            [_renderer_source("renderHeroMetrics"), _renderer_source("renderWelcomeFor")],
            "renderWelcomeFor({num: state.district.num, name: state.district.name})",
            {
                "state": {
                    "district": {"num": row["district_number"], "name": name},
                    "summary": [row],
                }
            },
        )
        markup = output["hero-kpis"]["innerHTML"].lower()
        assert f"fy {row['year']}" in markup
        assert "all funds / student" in markup
        assert "operations / student" in markup
        assert "construction" in markup and "debt" in markup
        title = output["picker-title"]["textContent"]
        assert title.startswith(f"{name} financial report")
        assert title.endswith(f"FY {row['year']}")
        with pytest.raises(AssertionError):
            assert "all funds / student" in markup.replace("all funds / student", "")
        with pytest.raises(AssertionError):
            assert "operations / student" in markup.replace("operations / student", "")
        with pytest.raises(AssertionError):
            assert "construction" in markup.replace("construction", "")


def test_the_hero_penny_caption_keeps_both_frames():
    """The personalised dollar caption led with the all-funds figure alone and
    the OWNER misread it as classroom spending — the exact Argyle failure, on
    a surface built weeks after the rule. The caption must carry the
    operating figure wherever construction is material."""
    dallas = json.loads(
        (ROOT / "tests" / "browser" / "fixtures" / "public-endpoints.json").read_text(encoding="utf-8")
    )["payloads"]["dallas_summary"][-1]
    dollar = {
        "year": dallas["year"],
        "perStudent": dallas["spend_per_student"],
        "enrollment": dallas["enrollment"],
        "total": dallas["total_spend"],
        "parts": [{"key": "classroom", "cents": 52, "color": "#123"}],
    }
    output = _render(
        [_renderer_source("renderHeroMetrics"), _renderer_source("updateHeroDollar")],
        "updateHeroDollar()",
        {
            "dollar": dollar,
            "state": {
                "district": {"name": dallas["district_name"]},
                "summary": [
                    {**dallas, "year": 2024, "operating_spend": 1, "enrollment": 1},
                    dallas,
                    {**dallas, "year": 2026, "operating_spend": 1, "enrollment": 1},
                ],
            },
        },
    )
    caption = output["tx-cap"]["innerHTML"].lower()
    ledger = output["hero-kpis"]["innerHTML"].lower()
    expected_ops = round(dallas["operating_spend"] / dallas["enrollment"])
    assert f"fy {dallas['year']}" in caption
    assert f"${expected_ops:,}" in caption
    assert "operations / student" in caption
    assert "all funds / student" in caption
    assert "construction" in caption and "debt" in caption
    assert f"${expected_ops:,}" in ledger
    with pytest.raises(AssertionError):
        assert f"${expected_ops:,}" in caption.replace(f"${expected_ops:,}", "$1")

    zero = _render(
        [_renderer_source("renderHeroMetrics"), _renderer_source("updateHeroDollar")],
        "updateHeroDollar()",
        {
            "dollar": dollar,
            "state": {
                "district": {"name": dallas["district_name"]},
                "summary": [{**dallas, "operating_spend": 0}],
            },
        },
    )["tx-cap"]["innerHTML"].lower()
    assert "$0" in zero and "operations / student" in zero

    unavailable = _render(
        [_renderer_source("renderHeroMetrics"), _renderer_source("updateHeroDollar")],
        "updateHeroDollar()",
        {
            "dollar": dollar,
            "state": {
                "district": {"name": dallas["district_name"]},
                "summary": [
                    {**dallas, "year": 2024, "operating_spend": 1, "enrollment": 1},
                    {**dallas, "operating_spend": None},
                ],
            },
        },
    )
    unavailable_caption = unavailable["tx-cap"]["innerHTML"].lower()
    unavailable_ledger = unavailable["hero-kpis"]["innerHTML"].lower()
    assert f"operations / student unavailable for fy {dallas['year']}" in unavailable_caption
    assert f"operations / student unavailable for fy {dallas['year']}" in unavailable_ledger


def test_the_equity_headline_states_its_school_year():
    """A percentage with no year reads as "now". TEA releases STAAR annually,
    so an undated figure quietly ages into a wrong impression without a single
    number changing — and this layer is currently a release behind, because the
    newer file sits behind a login. Being a release behind is defensible; being
    a release behind and undated is not."""
    from pathlib import Path
    s = (Path(__file__).resolve().parents[1] / "static" / "index.html").read_text()
    assert "function schoolYear(" in s, "the year renderer must exist"
    i_sub = s.index("$('eq-sub')")
    assert "schoolYear(e.year)" in s[i_sub:i_sub + 400], \
        "the equity sub-line must name the school year where it is read"
    # and the ambiguous form must not come back
    assert "`SY ${e.year}" not in s, \
        '"SY 2025" is ambiguous — it could be 2024-25 or 2025-26'
