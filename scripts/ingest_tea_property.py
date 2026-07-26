"""Ingest TEA property values, adopted tax rates and recapture into one table.

This is the "who pays" half of school finance. Our PEIMS data says where a
district's money goes and the Snapshot data says who its students are. Neither
says where the money came from, and in Texas that is the whole political
argument: a district's tax base, the rate the state lets it charge, and how
much of what it collects is taken back and sent elsewhere.

Three TEA sources, all public, all published as spreadsheets (TEA has no
finance API — this is the whole reason the pipeline looks like this):

1. Comptroller Property Tax Division values ("CPTD"), tax years 2015-2025.
   Certified taxable value per district. Tax year N funds school year N/N+1,
   which is TEA fiscal year N+1 — so tax year 2023 lines up with fiscal 2024.

2. School district adopted M&O and I&S tax rates, school years 2005-06 to
   2023-24, one row per district, two columns per year.

3. Recapture paid by district, fiscal 1994-2026, plus the Chapter 49
   designation flags for the two forthcoming years.

Why recapture is also derived and not just read
-----------------------------------------------
TEA reports `local_tax_revenue_from_m_o` NET of recapture, so any per-student
or per-dollar figure built on that column understates property-wealthy
districts badly — Austin ISD looks like a $93B tax base instead of $184B. The
recapture amount is recoverable from the finance file itself as the difference
between the two published revenue totals, and we compute it that way as well
as reading the official series. Agreement between the two is a data-quality
signal: they match to 0.7% median error over 3,623 district-years, so a
district where they diverge means one of the two files has an oddity worth
looking at rather than a number worth publishing.

Sources:
  https://tea.texas.gov/finance-and-grants/state-funding/additional-finance-resources/school-district-property-values-and-tax-rates
  https://tea.texas.gov/finance-and-grants/state-funding/excess-local-revenue
"""
from __future__ import annotations

import argparse
import re
import sys
import urllib.request
from pathlib import Path

import pandas as pd

TEA = "https://tea.texas.gov"
AFR = f"{TEA}/about-tea/state-funding/additional-finance-resources"
FILES = "{}/sites/default/files".format(TEA)

# Tax year -> URL. TEA moved the newer files to a different directory and
# switched underscores for hyphens partway through; both spellings are live.
CPTD = {
    **{y: f"{FILES}/cptd_{y}_final.xlsx" for y in (2015, 2016, 2017)},
    2018: f"{FILES}/cptd_2018_final.xls",
    2019: f"{FILES}/cptd-2019-final.xlsx",
    **{y: f"{AFR}/cptd-{y}-final.xlsx" for y in (2020, 2021, 2022, 2023, 2024)},
    2025: f"{AFR}/cptd-2025-preliminary-data.xlsx",
}
RATES = f"{AFR}/school-district-adopted-tax-rates-1.xlsx"
RECAPTURE = (f"{TEA}/about-tea/state-funding/state-funding-reports-and-data"
             f"/recapture-paid-by-district-1994-2026-nov-2025xlsx-0.xlsx")


def fetch(url: str, dest: Path) -> Path:
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  fetching {dest.name}", file=sys.stderr)
    with urllib.request.urlopen(url, timeout=120) as r:
        dest.write_bytes(r.read())
    return dest


def download(raw: Path) -> None:
    for year, url in CPTD.items():
        fetch(url, raw / Path(url).name)
        del year
    fetch(RATES, raw / "adopted_tax_rates.xlsx")
    fetch(RECAPTURE, raw / "recapture_1994_2026.xlsx")


def cdn(series: pd.Series) -> pd.Series:
    """District numbers are 6-digit strings; these files ship them as numbers,
    so 001902 arrives as 1902 and Cayuga ISD silently stops joining."""
    return (series.astype(str)
            .str.replace(r"\.0$", "", regex=True)
            .str.strip()
            .str.zfill(6))


def read_values(raw: Path) -> pd.DataFrame:
    """One row per district per tax year: certified taxable value.

    The CPTD sheets carry a two-row header — a merged title over a row of real
    column descriptions — so the labels live on row 1, not row 0. We take the
    local tax roll value (what the district actually levies against) and T2
    (the value the state's funding formulas use, after the homestead exemption
    and the over-65 tax ceiling). They differ, and which one is "the" tax base
    depends on the question, so keep both.
    """
    out = []
    for year, url in CPTD.items():
        path = raw / Path(url).name
        if not path.exists():
            print(f"  skip tax year {year} (not downloaded)", file=sys.stderr)
            continue
        df = pd.read_excel(path, header=1)
        df.columns = [re.sub(r"\s+", " ", str(c)).strip() for c in df.columns]
        roll = next((c for c in df.columns if "Local Tax Roll" in c), None)
        t2 = next((c for c in df.columns if c.startswith("T2")), None)
        if roll is None or t2 is None:
            print(f"  tax year {year}: no value column found, skipped", file=sys.stderr)
            continue
        part = pd.DataFrame({
            "district_number": cdn(df[df.columns[0]]),
            "tax_year": year,
            "taxable_value_roll": pd.to_numeric(df[roll], errors="coerce"),
            "taxable_value_t2": pd.to_numeric(df[t2], errors="coerce"),
        })
        out.append(part[part.district_number.str.fullmatch(r"\d{6}")])
    return pd.concat(out, ignore_index=True)


def read_rates(raw: Path) -> pd.DataFrame:
    """One row per district per school year: adopted M&O and I&S rates.

    Rates are per $100 of valuation. Charters have no rows here at all — they
    levy no property tax — which is why ~295 of our 1,310 districts never join.
    """
    df = pd.read_excel(raw / "adopted_tax_rates.xlsx")
    df.columns = [re.sub(r"\s+", " ", str(c)).strip() for c in df.columns]
    id_col = df.columns[0]
    rows = []
    for col in df.columns:
        m = re.match(r"^(\d{4})-(\d{4}) (M&O|I&S) Tax Rate$", col)
        if not m:
            continue
        rows.append(pd.DataFrame({
            "district_number": cdn(df[id_col]),
            # school year 2023-2024 is TEA fiscal 2024
            "year": int(m.group(2)),
            "kind": "mo" if m.group(3) == "M&O" else "is",
            "rate": pd.to_numeric(df[col], errors="coerce"),
        }))
    long = pd.concat(rows, ignore_index=True)
    wide = long.pivot_table(index=["district_number", "year"], columns="kind",
                            values="rate", aggfunc="first").reset_index()
    wide.columns.name = None
    return wide.rename(columns={"mo": "mo_rate", "is": "is_rate"})


def read_recapture(raw: Path) -> pd.DataFrame:
    """One row per district per fiscal year: recapture actually paid."""
    df = pd.read_excel(raw / "recapture_1994_2026.xlsx")
    df.columns = [re.sub(r"\s+", " ", str(c)).strip() for c in df.columns]
    cols = {}
    for c in df.columns:
        m = re.match(r"^\**\s*SY (\d{4}) Total Recapture$", c)
        if m:
            cols[c] = int(m.group(1))
    long = df.melt(id_vars=[df.columns[0]], value_vars=list(cols),
                   var_name="c", value_name="recapture_paid")
    long["district_number"] = cdn(long[df.columns[0]])
    long["year"] = long.c.map(cols)
    long["recapture_paid"] = pd.to_numeric(long.recapture_paid, errors="coerce").fillna(0.0)
    return long[["district_number", "year", "recapture_paid"]]


def build(raw: Path, finance_csv: Path) -> pd.DataFrame:
    fin = pd.read_csv(finance_csv, dtype={"district_number": str}, low_memory=False)
    keep = ["district_number", "district_name", "year", "fall_survey_enrollment",
            "all_funds_local_tax_revenue_from_m_o",
            "all_funds_local_property_taxes_from_i_s",
            "all_funds_state_revenue", "all_funds_federal_revenue",
            "all_funds_total_operating_revenue_and_other_revenue",
            "all_funds_total_operating_revenue_and_other_revenue_and_reca"]
    df = fin[keep].copy()
    df["recapture_derived"] = (
        df["all_funds_total_operating_revenue_and_other_revenue_and_reca"]
        - df["all_funds_total_operating_revenue_and_other_revenue"]).clip(lower=0)

    values = read_values(raw)
    # tax year N funds school year N/N+1 = TEA fiscal year N+1
    values["year"] = values.tax_year + 1
    df = df.merge(values.drop(columns="tax_year"), on=["district_number", "year"], how="left")
    df = df.merge(read_rates(raw), on=["district_number", "year"], how="left")
    df = df.merge(read_recapture(raw), on=["district_number", "year"], how="left")
    df["recapture_paid"] = df.recapture_paid.fillna(0.0)

    # Gross M&O collections: what the district's taxpayers actually paid,
    # before the state took its share back.
    df["mo_collections_gross"] = (df["all_funds_local_tax_revenue_from_m_o"]
                                  + df["recapture_paid"])
    df["total_tax_rate"] = df.mo_rate + df.is_rate
    df["wealth_per_student"] = df.taxable_value_roll / df.fall_survey_enrollment
    df["recapture_share_of_mo"] = (df.recapture_paid / df.mo_collections_gross).where(
        df.mo_collections_gross > 0)
    # QA: the tax base implied by collections should reproduce the certified
    # roll. Where it does not, one of the two source files has an oddity.
    implied = (df.mo_collections_gross * 100 / df.mo_rate).where(df.mo_rate > 0)
    df["value_check_pct"] = ((implied - df.taxable_value_roll)
                             / df.taxable_value_roll * 100).where(df.taxable_value_roll > 0)
    return df


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--download", action="store_true",
                    help="fetch the source spreadsheets from tea.texas.gov first")
    ap.add_argument("--raw", type=Path, default=Path("data/tea_property_raw"))
    ap.add_argument("--finance", type=Path, default=Path("data/texas_finance_clean.csv"))
    ap.add_argument("--out", type=Path, default=Path("data/tea_property.csv"))
    args = ap.parse_args()

    if args.download:
        download(args.raw)
    if not args.raw.exists():
        print(f"{args.raw} does not exist — run with --download first", file=sys.stderr)
        return 1

    df = build(args.raw, args.finance)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)

    have = df.dropna(subset=["taxable_value_roll", "mo_rate"])
    qa = have.value_check_pct.dropna()
    print(f"wrote {args.out} — {len(df):,} district-years")
    print(f"  with certified value + rate: {len(have):,} "
          f"({have.year.min():.0f}-{have.year.max():.0f})")
    print(f"  recapture: ${df.recapture_paid.sum() / 1e9:,.1f}B official vs "
          f"${df.recapture_derived.sum() / 1e9:,.1f}B derived")
    print(f"  tax-base QA: median {qa.median():+.1f}%, "
          f"{(qa.abs() < 10).mean() * 100:.0f}% within 10%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
