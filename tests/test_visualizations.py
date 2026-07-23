"""Smoke tests for visualization helpers using sample data."""
import matplotlib

matplotlib.use("Agg")  # no display in CI

from src.visualizations import (  # noqa: E402
    create_enrollment_vs_spending_scatter,
    create_interactive_trend,
    plot_district_comparison,
    plot_district_trend,
)

TREND_DATA = [
    {"year": 2018 + i, "spend_per_student": 10500 + 300 * i, "district_name": "DALLAS ISD"}
    for i in range(5)
]

SCATTER_DATA = [
    {"year": 2023, "enrollment": 1000 * (i + 1), "spend_per_student": 9000 + 200 * i,
     "district_name": f"DISTRICT {i}"}
    for i in range(10)
]


def test_plot_district_trend():
    plt = plot_district_trend(TREND_DATA, "DALLAS ISD")
    assert plt is not None
    plt.close("all")


def test_plot_district_comparison():
    data = [{"district_name": f"D{i}", "spend_per_student": 9000 + i * 500} for i in range(4)]
    plt = plot_district_comparison(data)
    assert plt is not None
    plt.close("all")


def test_create_interactive_trend():
    fig = create_interactive_trend(TREND_DATA, ["DALLAS ISD"])
    assert fig is not None


def test_create_enrollment_vs_spending_scatter():
    fig = create_enrollment_vs_spending_scatter(SCATTER_DATA, 2023)
    assert fig is not None
