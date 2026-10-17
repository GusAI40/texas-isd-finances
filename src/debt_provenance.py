"""Source context for BRB balances and separately dated district disclosures.

Reviews never replace the statewide BRB series. A matching principal does not
prove comparable interest assumptions, payment dates, or reporting periods.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

SCHEDULE_LIMIT = (
    "clears_in is the last year with a positive outstanding balance in the BRB "
    "schedule, not a verified final payment or maturity year. No exact BRB "
    "as-of date is established here beyond the fiscal-year label."
)


@lru_cache(maxsize=1)
def _reviews() -> dict:
    path = Path(__file__).resolve().parent.parent / "static" / "debt_source_reviews.json"
    return json.loads(path.read_text(encoding="utf-8"))


def context(data: dict, district_number: str) -> dict:
    meta = data["meta"]
    review = _reviews().get("districts", {}).get(district_number)
    limits = [*meta.get("limits", []), SCHEDULE_LIMIT]
    if review:
        limits.append(review["summary"])
    return {
        "fiscal_year": meta["fiscal_year"],
        "source": {"publisher": meta["publisher"], "url": meta["url"],
                   "fiscal_year": meta["fiscal_year"], "as_of_date": None,
                   "as_of_precision": "fiscal_year"},
        "schedule_year_basis": SCHEDULE_LIMIT,
        "source_review": review,
        "limits": limits,
    }
