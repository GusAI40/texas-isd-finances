"""Tests for data preparation helpers."""
from scripts.prepare_data import clean_district_number, to_snake_case


def test_clean_district_number_pads_to_six_digits():
    assert clean_district_number("57905") == "057905"
    assert clean_district_number(57905) == "057905"


def test_clean_district_number_strips_quotes():
    assert clean_district_number("'057905") == "057905"


def test_clean_district_number_handles_missing():
    assert clean_district_number(None) is None
    assert clean_district_number(float("nan")) is None


def test_to_snake_case():
    assert to_snake_case("DISTRICT NUMBER") == "district_number"
    assert to_snake_case("Gen Funds - Local Tax Revenue (M&O)") == "gen_funds_local_tax_revenue_m_o"


def test_to_snake_case_truncates_to_postgres_limit():
    assert len(to_snake_case("x" * 100)) <= 60
