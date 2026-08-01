"""
Data preparation script for Texas ISD financial data
Cleans and transforms Excel data for Supabase import
"""
import re
from pathlib import Path

import pandas as pd


def clean_district_number(x):
    """Clean district numbers - remove quotes, preserve leading zeros"""
    if pd.isna(x):
        return None
    s = str(x).strip().lstrip("'").lstrip("'")
    if s.isdigit():
        s = s.zfill(6)  # Ensure 6 digits with leading zeros
    return s

def to_snake_case(name):
    """Convert column names to snake_case"""
    s = name.strip().lower()
    s = re.sub(r'[^0-9a-zA-Z]+', '_', s)
    s = re.sub(r'_{2,}', '_', s).strip('_')
    return s[:60]  # Postgres column limit

def prepare_data(input_file, output_dir):
    """Main data preparation function"""
    print(f"Loading data from {input_file}...")
    df = pd.read_excel(input_file, sheet_name="DATAMART")

    # Clean district numbers
    print("Cleaning district numbers...")
    df["DISTRICT NUMBER"] = df["DISTRICT NUMBER"].apply(clean_district_number)

    # Rename columns to snake_case
    print("Converting column names to snake_case...")
    col_mapping = {}
    seen = set()
    for col in df.columns:
        base = to_snake_case(col)
        candidate = base
        i = 1
        while candidate in seen:
            candidate = f"{base}_{i}"
            i += 1
        seen.add(candidate)
        col_mapping[col] = candidate

    df.rename(columns=col_mapping, inplace=True)

    # Convert data types
    print("Converting data types...")
    for col in df.columns:
        if col in ("district_number", "district_name"):
            continue
        elif col == "year":
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int16")
        else:
            nums = pd.to_numeric(df[col], errors="coerce")
            if nums.notna().mean() >= 0.9:
                df[col] = nums

    # Save outputs
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)

    csv_path = output_dir / "texas_finance_clean.csv"
    print(f"Saving cleaned data to {csv_path}...")
    df.to_csv(csv_path, index=False)

    # Generate data dictionary
    print("Generating data dictionary...")
    data_dict = pd.DataFrame({
        "column_name": df.columns,
        "data_type": [str(df[col].dtype) for col in df.columns],
        "sample_value": [df[col].dropna().iloc[0] if df[col].notna().any() else None for col in df.columns],
        "non_null_count": [df[col].notna().sum() for col in df.columns],
        "null_count": [df[col].isna().sum() for col in df.columns]
    })

    dict_path = output_dir / "data_dictionary.csv"
    data_dict.to_csv(dict_path, index=False)

    print("Data preparation complete!")
    print(f"- Cleaned CSV: {csv_path}")
    print(f"- Data dictionary: {dict_path}")
    print(f"- Total rows: {len(df):,}")
    print(f"- Total columns: {len(df.columns)}")

    return df

if __name__ == "__main__":
    import argparse

    # This used to hardcode a filename from an older TEA release and crash with
    # a bare pandas traceback when it was missing — which reads like a broken
    # script rather than a missing input.
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", nargs="?",
                    default="ETL_2008-2024-summarized-financial-data-03-17-2025.xlsx",
                    help="TEA 'Summarized PEIMS Actual Financial Data' .xlsx "
                         "(download link in QUICKSTART.md)")
    ap.add_argument("-o", "--output-dir", default="data", help="default: data/")
    args = ap.parse_args()

    if not Path(args.input).exists():
        raise SystemExit(
            f"Input file not found: {args.input}\n\n"
            "Download the TEA 'Summarized PEIMS Actual Financial Data' release from\n"
            "https://tea.texas.gov/finance-and-grants/state-funding/"
            "state-funding-reports-and-data/peims-financial-data-downloads\n"
            "then pass it as an argument:\n"
            "    python scripts/prepare_data.py path/to/file.xlsx"
        )
    prepare_data(args.input, args.output_dir)
