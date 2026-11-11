"""Tests for parsing CDE Lightband public rate pages."""
from pathlib import Path

from custom_components.cde_lightband.cde_api import (
    CdeRateData,
    parse_internet_prices_html,
    parse_rates_html,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_rates_html_extracts_residential_table():
    rates = parse_rates_html((FIXTURES / "rates_page.html").read_text(encoding="utf-8"))
    assert rates is not None
    assert rates.customer_charge == 30.50
    assert rates.energy_rate == 0.11010
    assert rates.grid_access_tiers == [(1000.0, 2.00), (2000.0, 4.00), (None, 7.00)]
    assert rates.rate_month == "November 2026"


def test_parse_rates_html_garbage_returns_none():
    assert parse_rates_html("<html><body>hello</body></html>") is None
    assert parse_rates_html("") is None


def test_grid_access_charge_tiers():
    rates = CdeRateData(
        energy_rate=0.11,
        customer_charge=30.5,
        grid_access_tiers=[(1000.0, 2.0), (2000.0, 4.0), (None, 7.0)],
        rate_month="November 2026",
    )
    assert rates.grid_access_charge(500) == 2.0
    assert rates.grid_access_charge(1000) == 2.0
    assert rates.grid_access_charge(1001) == 4.0
    assert rates.grid_access_charge(2000) == 4.0
    assert rates.grid_access_charge(2001) == 7.0


def test_parse_internet_prices_html():
    prices = parse_internet_prices_html(
        (FIXTURES / "internet_page.html").read_text(encoding="utf-8")
    )
    assert prices == {"300": 53.95, "600": 73.95, "1000": 94.95, "2500": 123.95}


def test_parse_internet_prices_html_garbage_returns_none():
    assert parse_internet_prices_html("<p>no prices here</p>") is None
