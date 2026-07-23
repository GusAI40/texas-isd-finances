# UX Research — Dashboard Design via Monte Carlo User Simulation

**Date:** July 2026 · **Method:** seeded Monte Carlo simulation ·
**Reproduce:** `python scripts/simulate_admin_usage.py` (seed 42) ·
**Raw output:** `docs/simulation_results.json`

## Question

If Texas school administrators — not engineers — decided what this dashboard
shows, what would it show? We simulated the users before designing the UI,
so the design serves measured demand rather than builder intuition.

## Method

1. **Population (real data — the source of truth).** 1,000 simulated
   administrators assigned to the **1,202 real districts** in the latest
   fiscal year (2025) of the TEA dataset, weighted by √enrollment (admin
   headcount scales sub-linearly with district size). Anomaly exposure is
   real too: 15.2% of districts had an actual revenue-drop or
   enrollment-decline event in the last two data years, and admins in those
   districts investigate flags 3× more often.
2. **Personas (modeled assumptions, documented here).** CFO/business manager
   32%, principal 22%, superintendent 18%, board trustee 15%,
   communications/admin staff 13% — weighted toward the roles that actually
   consume district financial data. Each persona has its own task-probability
   profile (see the script).
3. **Sessions.** Each admin runs ~6 sessions/month (Poisson), 1–3 tasks per
   session → **5,990 sessions, 11,991 task events**. Seeded (42) so anyone
   can re-run and get identical numbers.

**Honesty note:** this is a *simulation*, not a survey. The district
population, sizes, and anomaly incidence are real; the persona mix and task
priors are explicit, inspectable modeling assumptions in
`scripts/simulate_admin_usage.py`. When real usage analytics or admin
interviews become available, they replace these priors.

## Findings — what the simulated admins actually wanted

| Rank | Demand | Share | Dashboard answer (shipped) |
|---|---|---|---|
| 1 | "How do we compare with similar-size districts?" | **16.1%** | Peer-comparison chart: the 12 closest-size districts, your bar highlighted, state median marked |
| 2 | "How have we changed over the years?" | 13.8% | 17-year trend chart with metric tabs (spend/student, enrollment, revenue vs spend) |
| 3 | "Get a defensible number for a board meeting" | 11.5% | Big KPI tiles + Print (board-packet view) + CSV download |
| 4 | "What's normal statewide?" | 10.6% | Statewide-median dashed line on every spend chart + percentile tile ("spends more than X% of districts") |
| 5 | "Where does the money actually go?" | 10.5% | Money-breakdown bars: instruction / debt / building projects / other |
| 6 | "We got flagged — what does it mean?" | 8.6% | Per-district flag cards with plain-English cause AND innocent explanations to rule out |
| 7 | "Is our enrollment decline a trend or a blip?" | 7.1% | Enrollment tab on the trend chart |
| 8 | "Export/print the numbers" | 6.0% | CSV + print stylesheet |
| 9 | "What is our neighbor district doing?" | 5.4% | District picker works for any district, remembered per device |
| 10 | "Answer a parent/press question simply" | 4.1% | Plain-English captions under every number |
| 11 | "Verify against official TEA figures" | 3.8% | TEA source links in the ask-box note and disclaimer |
| 12 | "Odd one-off questions" | **2.3%** | Natural-language ask box — kept, but moved to the bottom |

## The headline design lesson

The pre-redesign UI led with the natural-language question box — the
**lowest-demand** feature (2.3%) — and had **zero** support for the top four
demands (peers, trends-with-context, board-ready output, statewide median).
The redesign inverts the page to match the demand ranking top-to-bottom.
Segment analysis backed the order: peer comparison ranked #1 for every
district size bucket and every persona except communications staff.

## Design principles applied (the "8th-grader test")

- Every number carries a plain-English caption ("Spends more per student
  than 62% of Texas districts"), not just a value.
- Context before judgment: nothing is red/green "good/bad"; the median line
  and percentile let readers judge.
- Flags de-escalated by design: each card lists innocent explanations first
  — a flag is a question, not an accusation.
- 60-second guided tour on first visit (replayable via 🎓 Tutorial).
- Accessible fallbacks: every chart has a data-table twin; charts use one
  hue plus neutral references; light/dark themes.

## New API endpoints this research drove

| Endpoint | Serves demand # |
|---|---|
| `GET /district/{id}/peers` | 1, 4 (cohort + statewide percentile + median) |
| `GET /benchmarks` | 2, 4 (statewide medians per year) |
| `GET /anomalies?district_number=` | 6 (one district's flags) |
