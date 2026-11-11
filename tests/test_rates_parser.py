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


def _rates_section_with_preceding_note_row() -> str:
    """Real fixture with a 3-cell non-header table before the rate table."""
    fixture = (FIXTURES / "rates_page.html").read_text(encoding="utf-8")
    note_table = (
        '<table class="mtr-table"><tr>'
        '<td><div class="mtr-cell-content">Schedule</div></td>'
        '<td><div class="mtr-cell-content">Effective</div></td>'
        '<td><div class="mtr-cell-content">January 2025</div></td>'
        "</tr></table>"
    )
    return fixture.replace("<figure", note_table + "<figure", 1)


def test_parse_rates_html_ignores_rows_before_rate_table_header():
    """A stray 3-cell row above the rate table must not become the header row."""
    rates = parse_rates_html(_rates_section_with_preceding_note_row())
    assert rates is not None
    assert rates.rate_month == "November 2026"
    assert rates.customer_charge == 30.50


def test_parse_rates_html_missing_header_row_returns_none():
    """No 'Retail Rate' header row in the section -> not parseable."""
    fixture = (FIXTURES / "rates_page.html").read_text(encoding="utf-8")
    mangled = fixture.replace("November 2026 Retail Rate", "November 2026")
    assert parse_rates_html(mangled) is None


def test_parse_rates_html_missing_customer_row_returns_none():
    fixture = (FIXTURES / "rates_page.html").read_text(encoding="utf-8")
    mangled = fixture.replace("$30.50", "$0.00</div></td><td><div class=\"mtr-cell-content\">Junk")
    assert parse_rates_html(mangled) is None
