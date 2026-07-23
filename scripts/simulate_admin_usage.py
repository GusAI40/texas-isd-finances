"""
Monte Carlo simulation of Texas school administrator usage.

Simulates 1,000 administrators drawn from REAL district data (the cleaned
TEA dataset is the source of truth for district sizes, spending levels, and
anomaly incidence), assigns research-grounded personas, and generates a
month of usage sessions per admin. The output is a ranked demand table of
features/questions, used to drive dashboard design (docs/UX_RESEARCH.md).

Personas and task priors are modeled assumptions (documented in
UX_RESEARCH.md); the district population, enrollment weighting, and anomaly
exposure come from the real data. Seeded for reproducibility.

Run: python scripts/simulate_admin_usage.py [data/texas_finance_clean.csv]
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
N_ADMINS = 1000

# Persona mix for finance-data consumers in a district office. Weights are
# modeled from who actually handles TEA financial data day-to-day: business
# offices dominate, then campus/executive leadership, then trustees/comms.
PERSONAS = {
    "cfo_business_manager": 0.32,
    "superintendent": 0.18,
    "principal": 0.22,
    "board_trustee": 0.15,
    "comms_or_admin_staff": 0.13,
}

# Task library. Each task maps to the dashboard feature that serves it.
TASKS = {
    "peer_comparison": "How do we compare with similar-size districts?",
    "trend_over_time": "How has our spending/enrollment changed over the years?",
    "board_packet_number": "Grab a defensible number/chart for a board meeting",
    "explain_flag": "We got flagged — what does it mean and is it right?",
    "spend_breakdown": "Where does our money actually go? (instruction/debt/capital)",
    "statewide_context": "What's normal statewide? (median, our percentile)",
    "enrollment_worry": "Is our enrollment decline a trend or a blip?",
    "neighbor_lookup": "What is district X (neighbor/rival) doing?",
    "export_data": "Export/print the numbers for a spreadsheet or slide",
    "verify_tea": "Verify a number against official TEA figures",
    "parent_question": "Answer a parent/press question in plain English",
    "freeform_question": "Ask an odd one-off question (natural language)",
}

# Per-persona task probabilities (rows sum to 1). Modeled: CFOs live in
# benchmarks and breakdowns; superintendents prep board/context; principals
# care about their campus context and comparisons; trustees verify and ask
# plain-language questions; comms answer the public.
TASK_PRIORS = {
    "cfo_business_manager": dict(peer_comparison=.20, trend_over_time=.15, board_packet_number=.12,
                                 explain_flag=.08, spend_breakdown=.14, statewide_context=.10,
                                 enrollment_worry=.05, neighbor_lookup=.04, export_data=.07,
                                 verify_tea=.03, parent_question=.01, freeform_question=.01),
    "superintendent": dict(peer_comparison=.18, trend_over_time=.14, board_packet_number=.18,
                           explain_flag=.09, spend_breakdown=.08, statewide_context=.12,
                           enrollment_worry=.08, neighbor_lookup=.05, export_data=.03,
                           verify_tea=.02, parent_question=.02, freeform_question=.01),
    "principal": dict(peer_comparison=.15, trend_over_time=.16, board_packet_number=.06,
                      explain_flag=.05, spend_breakdown=.12, statewide_context=.12,
                      enrollment_worry=.12, neighbor_lookup=.08, export_data=.05,
                      verify_tea=.02, parent_question=.04, freeform_question=.03),
    "board_trustee": dict(peer_comparison=.16, trend_over_time=.12, board_packet_number=.10,
                          explain_flag=.10, spend_breakdown=.10, statewide_context=.10,
                          enrollment_worry=.06, neighbor_lookup=.04, export_data=.04,
                          verify_tea=.08, parent_question=.06, freeform_question=.04),
    "comms_or_admin_staff": dict(peer_comparison=.08, trend_over_time=.10, board_packet_number=.12,
                                 explain_flag=.06, spend_breakdown=.08, statewide_context=.08,
                                 enrollment_worry=.04, neighbor_lookup=.06, export_data=.12,
                                 verify_tea=.06, parent_question=.14, freeform_question=.06),
}


def size_bucket(enrollment):
    if enrollment < 1000:
        return "small(<1k)"
    if enrollment < 10000:
        return "medium(1k-10k)"
    return "large(10k+)"


def main(csv_path="data/texas_finance_clean.csv"):
    rng = np.random.default_rng(SEED)

    df = pd.read_csv(csv_path, dtype={"district_number": str})
    latest = df[df.year == df.year.max()].dropna(subset=["fall_survey_enrollment"])
    latest = latest[latest.fall_survey_enrollment > 0]

    # Real anomaly incidence: approximate flag exposure from the data itself
    # (YoY revenue drop >15% or enrollment decline >10% in any recent year).
    recent = df[df.year >= df.year.max() - 2].copy()
    recent.sort_values(["district_number", "year"], inplace=True)
    grp = recent.groupby("district_number")
    rev_prev = grp["all_funds_total_operating_revenue"].shift(1)
    enr_prev = grp["fall_survey_enrollment"].shift(1)
    flagged = recent[
        ((recent.all_funds_total_operating_revenue - rev_prev) / rev_prev < -0.15)
        | ((recent.fall_survey_enrollment - enr_prev) / enr_prev < -0.10)
    ]["district_number"].unique()

    # Admin headcount scales sub-linearly with enrollment: weight by sqrt.
    weights = np.sqrt(latest.fall_survey_enrollment.to_numpy())
    weights = weights / weights.sum()
    admin_district_idx = rng.choice(len(latest), size=N_ADMINS, p=weights)
    persona_names = list(PERSONAS)
    admin_personas = rng.choice(persona_names, size=N_ADMINS, p=list(PERSONAS.values()))

    feature_hits = Counter()
    by_size = defaultdict(Counter)
    by_persona = defaultdict(Counter)
    session_count = 0
    flagged_admins_who_investigate = 0
    flagged_admins = 0

    for i in range(N_ADMINS):
        row = latest.iloc[admin_district_idx[i]]
        persona = admin_personas[i]
        bucket = size_bucket(row.fall_survey_enrollment)
        in_flagged_district = row.district_number in flagged
        if in_flagged_district:
            flagged_admins += 1

        priors = TASK_PRIORS[persona].copy()
        # Admins in actually-flagged districts investigate flags far more.
        if in_flagged_district:
            priors["explain_flag"] *= 3.0
        total = sum(priors.values())
        tasks, probs = zip(*[(t, p / total) for t, p in priors.items()])

        # ~6 sessions/month, 1-3 tasks per session
        n_sessions = max(1, rng.poisson(6))
        session_count += n_sessions
        investigated = False
        for _ in range(n_sessions):
            for task in rng.choice(tasks, size=1 + rng.integers(0, 3), p=probs):
                feature_hits[task] += 1
                by_size[bucket][task] += 1
                by_persona[persona][task] += 1
                if task == "explain_flag":
                    investigated = True
        if in_flagged_district and investigated:
            flagged_admins_who_investigate += 1

    total_hits = sum(feature_hits.values())
    demand = [
        {
            "task": t,
            "question": TASKS[t],
            "hits": feature_hits[t],
            "share_pct": round(100 * feature_hits[t] / total_hits, 1),
        }
        for t in sorted(TASKS, key=lambda t: -feature_hits[t])
    ]

    results = {
        "seed": SEED,
        "n_admins": N_ADMINS,
        "n_sessions": session_count,
        "n_task_events": total_hits,
        "source_of_truth": {
            "districts_in_population": int(len(latest)),
            "latest_year": int(df.year.max()),
            "flagged_district_share_pct": round(100 * len(flagged) / len(latest), 1),
        },
        "admins_in_flagged_districts": flagged_admins,
        "flag_investigation_rate_pct": round(
            100 * flagged_admins_who_investigate / max(1, flagged_admins), 1),
        "demand_ranking": demand,
        "by_size": {k: dict(v.most_common(5)) for k, v in by_size.items()},
        "by_persona": {k: dict(v.most_common(5)) for k, v in by_persona.items()},
    }

    out = Path("docs/simulation_results.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(results, indent=2))
    print(f"Simulated {N_ADMINS} admins, {session_count} sessions, {total_hits} task events")
    print(f"Population: {len(latest)} real districts, latest year {df.year.max()}, "
          f"{results['source_of_truth']['flagged_district_share_pct']}% recently flagged")
    print("\nDemand ranking:")
    for d in demand:
        print(f"  {d['share_pct']:5.1f}%  {d['task']:22s} {d['question']}")
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main(*sys.argv[1:])
