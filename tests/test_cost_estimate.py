"""Tests for service cost estimates built from the pieces of past visits."""

from pathlib import Path

import pytest

from sales_assistant.cost_estimate import (
    CostQuestion,
    PartNeed,
    describe_estimate,
    estimate_visit,
)
from sales_assistant.service_records import (
    RECORDS_FILE,
    CostLine,
    Equipment,
    Flag,
    JobType,
    LineKind,
    ServiceRecord,
    load_records,
)
from tests.samples import make_record

REAL_RECORDS = Path(__file__).parents[1] / ".cache" / RECORDS_FILE

CLOTH = CostLine(
    description="PF-DS Filter Cloth", kind=LineKind.PART, quantity=12, unit_price=98, amount=1176
)
CHILE_VISIT = {
    "country": "Chile",
    "currency": "USD",
    "equipment": Equipment.COLUMNCELL,
    "job_types": [JobType.INSPECTION_AND_CLEANING],
}
RECORDS = [
    make_record("FSR-A", on_site_hours=8.0, cost_lines=[CLOTH]),
    make_record("FSR-B", on_site_hours=12.0, country="Canada", currency="CAD", cost_lines=[CLOTH]),
    make_record("FSR-C", travel_hours=2.0, labour_rate=110, travel_rate=75, **CHILE_VISIT),
    make_record("FSR-D", travel_hours=6.0, labour_rate=90, travel_rate=65, **CHILE_VISIT),
]
CLOTHS_IN_CHILE = CostQuestion(
    equipment=Equipment.LAROX_PF_DS,
    job_type=JobType.FILTER_CLOTH_REPLACEMENT,
    country="Chile",
    parts=[PartNeed(name="filter cloths", quantity=10)],
)


def test_the_typical_total_takes_the_middle_value_of_each_piece() -> None:
    estimate = estimate_visit(RECORDS, CLOTHS_IN_CHILE)

    # Hours 10 x rate 100, travel 4 h x 70, and 10 cloths at the middle of USD 105.84 and 71.54.
    assert estimate.currency == "USD"
    assert estimate.typical == pytest.approx(10 * 100 + 4 * 70 + 10 * (105.84 + 71.54) / 2)
    assert estimate.combinations == 2 * 2 * 2 * 2 * 2
    assert estimate.reports == ["FSR-A", "FSR-B", "FSR-C", "FSR-D"]


def test_the_likely_range_leaves_out_the_cheapest_and_dearest_tenth_of_combinations() -> None:
    chile = make_record("FSR-C", travel_hours=4.0, labour_rate=100, travel_rate=70, **CHILE_VISIT)
    records = [make_record("FSR-A", on_site_hours=8.0), make_record("FSR-B", on_site_hours=12.0)]
    question = CLOTHS_IN_CHILE.model_copy(update={"parts": []})

    estimate = estimate_visit([*records, chile], question)

    # Two possible totals, 1,080 and 1,480: a tenth of the way in from each end.
    assert estimate.likely_range == pytest.approx((1120, 1440))


def test_weekend_and_emergency_visits_are_left_out() -> None:
    weekend = make_record("FSR-W", weekend=True, labour_rate=185, travel_rate=100, **CHILE_VISIT)
    emergency = make_record("FSR-E", emergency=True, on_site_hours=30.0)

    estimate = estimate_visit([*RECORDS, weekend, emergency], CLOTHS_IN_CHILE)

    assert "FSR-W" not in estimate.reports
    assert "FSR-E" not in estimate.reports


def test_prices_are_converted_into_the_currency_of_the_countrys_own_reports() -> None:
    text = describe_estimate(estimate_visit(RECORDS, CLOTHS_IN_CHILE))

    assert "filter cloths, each: 72 / 89 / 106 USD (FSR-A, FSR-B)" in text
    assert "1 CAD = 0.73 USD, 1 EUR = 1.08 USD" in text


def test_a_country_without_rates_gets_no_total_and_says_what_is_missing() -> None:
    question = CLOTHS_IN_CHILE.model_copy(update={"country": "Russia"})

    estimate = estimate_visit(RECORDS, question)
    text = describe_estimate(estimate)

    assert estimate.typical is None
    assert "No total" in text
    assert "no labour rate for Russia; no travel time for Russia" in text


def test_a_part_without_an_invoice_price_is_named_and_left_out_of_the_total() -> None:
    question = CLOTHS_IN_CHILE.model_copy(update={"parts": [PartNeed(name="rotor", quantity=2)]})

    estimate = estimate_visit(RECORDS, question)

    assert estimate.typical == pytest.approx(10 * 100 + 4 * 70)
    assert "no invoice price for rotor on larox_pf_ds" in describe_estimate(estimate)


def test_a_flag_warns_only_where_it_touches_what_the_record_gives() -> None:
    hours_off = make_record("FSR-H", on_site_hours=9.0, flags=[Flag.HOURS_MISMATCH])
    dollar_sign = make_record(
        "FSR-S", travel_hours=5.0, flags=[Flag.CURRENCY_ASSUMED], **CHILE_VISIT
    )

    estimate = estimate_visit([*RECORDS, hours_off, dollar_sign], CLOTHS_IN_CHILE)

    assert estimate.warnings == ("FSR-H: its task hours do not add up to its hours on site",)


def test_the_text_for_the_model_carries_every_number_already_computed() -> None:
    text = describe_estimate(estimate_visit(RECORDS, CLOTHS_IN_CHILE))

    assert "Typical total: 2,167. Likely range:" in text
    assert "Typical by part of the total: labour 1,000, travel 280, filter cloths (10) 887." in text
    assert "- hours on site: 8.0 / 10.0 / 12.0 h (FSR-A, FSR-B)" in text


@pytest.fixture(name="real_records", scope="module")
def fixture_real_records() -> list[ServiceRecord]:
    """The records ingest wrote from the real reports; the test skips until they exist."""
    if not REAL_RECORDS.exists():
        pytest.skip("no service records yet: run `sales-assistant ingest` with OPENAI_API_KEY set")
    return load_records(REAL_RECORDS)


def test_real_estimate_for_demo_prompt_2_matches_the_hand_calculation(
    real_records: list[ServiceRecord],
) -> None:
    question = CLOTHS_IN_CHILE.model_copy(
        update={"parts": [PartNeed(name="filter cloth", quantity=12)]}
    )

    estimate = estimate_visit(real_records, question)

    # 8.6 h x USD 110, 8.6 h of travel x USD 75, and 12 cloths at USD 72 (from CAD and EUR).
    assert estimate.typical == pytest.approx(2449, abs=1)
    assert estimate.likely_range == pytest.approx((1759, 3072), abs=1)
    assert estimate.combinations == 648
    assert estimate.reports == [
        "FSR-0001",
        "FSR-0014",
        "FSR-0015",
        "FSR-0027",
        "FSR-0028",
        "FSR-0031",
        "FSR-0034",
        "FSR-0035",
        "FSR-0037",
        "FSR-0044",
    ]
