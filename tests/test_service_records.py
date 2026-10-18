"""Tests for reading service reports into checked records."""

import json
from collections import Counter
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from sales_assistant.service_records import (
    RECORDS_FILE,
    CostLine,
    CostStatus,
    Equipment,
    Flag,
    JobType,
    LineKind,
    RecordError,
    ReportReading,
    ServiceRecord,
    check_reading,
    load_records,
    read_reports,
    save_records,
    write_records,
)
from tests.samples import LINES, make_reading

REAL_RECORDS = Path(__file__).parents[1] / ".cache" / RECORDS_FILE


def test_check_reading_takes_the_rates_and_total_of_a_clean_report_and_flags_nothing() -> None:
    record = check_reading("FSR-0027", make_reading())

    assert record.report_id == "FSR-0027"
    assert (record.cost_status, record.labour_rate, record.travel_rate) == ("itemized", 78, 62)
    assert record.total_ex_vat == 2135.0
    assert record.flags == []


@pytest.mark.parametrize(
    ("cost_lines", "total", "status"),
    [
        (LINES, 2135.0, CostStatus.ITEMIZED),
        (LINES, None, CostStatus.CUT_OFF),
        ([], 2135.0, CostStatus.TOTAL_ONLY),
        ([], None, CostStatus.NOT_STATED),
    ],
)
def test_cost_status_follows_what_the_report_states(
    cost_lines: list[CostLine], total: float | None, status: CostStatus
) -> None:
    record = check_reading("FSR-0001", make_reading(cost_lines=cost_lines, total=total))

    assert record.cost_status == status


def test_vat_is_taken_off_the_total_and_flagged() -> None:
    record = check_reading("FSR-0031", make_reading(total=2647.4, vat=512.4))

    assert record.total_ex_vat == 2135.0
    assert record.flags == [Flag.VAT_REMOVED]


def test_lines_that_do_not_add_up_to_the_total_are_flagged() -> None:
    record = check_reading("FSR-0001", make_reading(total=2500.0))

    assert record.flags == [Flag.TOTAL_MISMATCH]


def test_hours_times_rate_that_miss_a_lines_amount_are_flagged() -> None:
    labour = CostLine(
        description="Labour", kind=LineKind.LABOUR, quantity=8.4, unit_price=78, amount=700
    )
    reading = make_reading(cost_lines=[LINES[0], labour, LINES[2]], total=2179.8)

    assert check_reading("FSR-0001", reading).flags == [Flag.RATE_MISMATCH]


def test_task_hours_that_miss_the_hours_on_site_are_flagged() -> None:
    reading = make_reading(task_hours=[0.5, 0.5, 1.75, 2.75, 0.67, 1.5, 1.08])

    assert check_reading("FSR-0027", reading).flags == [Flag.HOURS_MISMATCH]


def test_a_cost_that_names_no_currency_is_read_as_us_dollars_and_flagged() -> None:
    record = check_reading("FSR-0003", make_reading(currency=None, cost_lines=[], total=2540.0))

    assert record.currency == "USD"
    assert record.flags == [Flag.CURRENCY_ASSUMED]


def test_a_cost_line_without_a_single_number_is_dropped() -> None:
    empty = CostLine(
        description="as per agreement",
        kind=LineKind.LABOUR,
        quantity=None,
        unit_price=None,
        amount=None,
    )
    reading = make_reading(cost_lines=[empty], total=None, currency=None)

    record = check_reading("FSR-0030", reading)

    assert record.cost_lines == []
    assert (record.cost_status, record.currency, record.flags) == ("not_stated", None, [])


def test_a_report_without_a_cost_gets_no_currency() -> None:
    record = check_reading("FSR-0016", make_reading(currency=None, cost_lines=[], total=None))

    assert record.currency is None
    assert record.flags == []


@pytest.mark.parametrize(
    ("visit_date", "flags"),
    [("08/12/24", [Flag.DATE_AMBIGUOUS]), ("2023-10-19 (Weekend Visit)", [])],
)
def test_a_date_is_ambiguous_unless_it_starts_year_first(
    visit_date: str, flags: list[Flag]
) -> None:
    assert check_reading("FSR-0016", make_reading(visit_date=visit_date)).flags == flags


def reading_named_after_its_report(request: str) -> ReportReading:
    """A reading whose customer is the report it was asked about, so a mix-up would show."""
    report_id = request.rsplit("Report ", 1)[1].split(":")[0]
    return make_reading(customer=report_id)


def test_write_records_keeps_saved_records_and_reads_the_others_in_report_order() -> None:
    reports = {"FSR-0001": "one", "FSR-0002": "two", "FSR-0003": "three"}
    saved = check_reading("FSR-0002", make_reading(customer="Saved earlier"))
    read = Mock(side_effect=reading_named_after_its_report)

    records = write_records(reports, read, [saved])

    assert [record.customer for record in records] == ["FSR-0001", "Saved earlier", "FSR-0003"]
    assert read.call_count == 2


def test_read_reports_reads_each_text_file_under_its_report_id(reports_folder: Path) -> None:
    reports = read_reports(reports_folder)

    assert list(reports) == ["FSR-0001"]
    assert "Total: EUR 2,215.40" in reports["FSR-0001"]


def test_read_reports_needs_at_least_one_report(tmp_path: Path) -> None:
    with pytest.raises(RecordError, match="No service reports found"):
        read_reports(tmp_path)


def test_load_records_reads_back_what_save_records_wrote(tmp_path: Path) -> None:
    records = [check_reading("FSR-0027", make_reading())]
    save_records(records, tmp_path / RECORDS_FILE)

    assert load_records(tmp_path / RECORDS_FILE) == records


def test_load_records_asks_for_ingest_with_a_key_when_nothing_was_saved(tmp_path: Path) -> None:
    with pytest.raises(RecordError, match="with OPENAI_API_KEY set"):
        load_records(tmp_path / RECORDS_FILE)


def test_load_records_asks_to_rewrite_records_saved_in_an_older_format(tmp_path: Path) -> None:
    saved = check_reading("FSR-0027", make_reading()).model_dump(mode="json")
    (tmp_path / RECORDS_FILE).write_text(json.dumps([saved | {"flags": ["retired_flag"]}]))

    with pytest.raises(RecordError, match="ingest --rewrite"):
        load_records(tmp_path / RECORDS_FILE)


# Checked by hand against the reports: one report per layout and per trap.
HAND_CHECKED: dict[str, dict[str, Any]] = {
    "FSR-0001": {
        "equipment": Equipment.COLUMNCELL,
        "country": "Chile",
        "on_site_hours": 12.3,
        "travel_hours": 2.2,
        "currency": "USD",
        "labour_rate": 110,
        "travel_rate": 75,
        "total_ex_vat": 1639,
        "cost_status": CostStatus.ITEMIZED,
        "flags": [],
    },
    "FSR-0003": {
        "equipment": Equipment.ORION_PUMP,
        "country": "Russia",
        "on_site_hours": 9.2,
        "travel_hours": 6.5,
        "currency": "USD",
        "total_ex_vat": 2540,
        "cost_status": CostStatus.TOTAL_ONLY,
        "flags": [Flag.CURRENCY_ASSUMED],
    },
    "FSR-0012": {
        "equipment": Equipment.ORION_PUMP,
        "country": "Zambia",
        "on_site_hours": 15.4,
        "travel_hours": 10.1,
        "currency": "USD",
        "labour_rate": 85,
        "travel_rate": 65,
        "total_ex_vat": 2069.5,
        "cost_status": CostStatus.ITEMIZED,
        "flags": [Flag.HOURS_MISMATCH],
    },
    "FSR-0016": {
        "equipment": Equipment.CELLSTATION,
        "country": "Australia",
        "on_site_hours": None,
        "travel_hours": None,
        "currency": None,
        "cost_status": CostStatus.NOT_STATED,
        "flags": [Flag.DATE_AMBIGUOUS],
    },
    "FSR-0019": {
        "equipment": Equipment.COLUMNCELL,
        "country": "Canada",
        "on_site_hours": 6.7,
        "travel_hours": 4.4,
        "currency": "CAD",
        "labour_rate": 185,
        "travel_rate": 110,
        "total_ex_vat": 1835.5,
        "weekend": True,
        "flags": [],
    },
    "FSR-0026": {
        "equipment": Equipment.LAROX_PF,
        "country": "Sweden",
        "on_site_hours": 12.8,
        "travel_hours": 7.9,
        "currency": "SEK",
        "labour_rate": 950,
        "travel_rate": 700,
        "total_ex_vat": 17690,
        "customer_parts": True,
        "flags": [],
    },
    "FSR-0027": {
        "equipment": Equipment.LAROX_PF_DS,
        "country": "Sweden",
        "on_site_hours": 8.4,
        "travel_hours": 4.9,
        "currency": "EUR",
        "labour_rate": 78,
        "travel_rate": 62,
        "total_ex_vat": None,
        "cost_status": CostStatus.CUT_OFF,
        "flags": [Flag.HOURS_MISMATCH],
    },
    "FSR-0031": {
        "equipment": Equipment.LAROX_PF_DS,
        "country": "Finland",
        "on_site_hours": 6.2,
        "travel_hours": 6.2,
        "currency": "EUR",
        "labour_rate": 85,
        "travel_rate": 55,
        "total_ex_vat": 2081,
        "cost_status": CostStatus.ITEMIZED,
        "flags": [Flag.VAT_REMOVED],
    },
    "FSR-0035": {
        "equipment": Equipment.FILTER_OPTIMIZER,
        "country": "Chile",
        "on_site_hours": 8.4,
        "travel_hours": 10.1,
        "currency": "USD",
        "total_ex_vat": 2850,
        "cost_status": CostStatus.TOTAL_ONLY,
        "flags": [],
    },
    "FSR-0046": {
        "equipment": Equipment.COLUMNCELL,
        "country": "Chile",
        "on_site_hours": 12.5,
        "travel_hours": None,
        "cost_status": CostStatus.NOT_STATED,
        "flags": [Flag.DATE_AMBIGUOUS],
    },
}
# The reports carrying each flag, found by hand.
HAND_FLAGGED = {
    Flag.TOTAL_MISMATCH: set(),
    Flag.RATE_MISMATCH: set(),
    Flag.VAT_REMOVED: {"FSR-0031"},
    Flag.HOURS_MISMATCH: {"FSR-0012", "FSR-0027", "FSR-0048"},
    Flag.CURRENCY_ASSUMED: {"FSR-0003", "FSR-0004", "FSR-0007"},
    Flag.DATE_AMBIGUOUS: {
        "FSR-0016",
        "FSR-0017",
        "FSR-0018",
        "FSR-0028",
        "FSR-0029",
        "FSR-0030",
        "FSR-0036",
        "FSR-0038",
        "FSR-0039",
        "FSR-0046",
        "FSR-0050",
    },
}
PF_DS_CLOTH_JOBS = {"FSR-0014", "FSR-0027", "FSR-0028", "FSR-0031", "FSR-0037", "FSR-0044"}


@pytest.fixture(name="real_records", scope="module")
def fixture_real_records() -> dict[str, ServiceRecord]:
    """The records ingest wrote from the real reports; the tests skip until they exist."""
    if not REAL_RECORDS.exists():
        pytest.skip("no service records yet: run `sales-assistant ingest` with OPENAI_API_KEY set")
    return {record.report_id: record for record in load_records(REAL_RECORDS)}


@pytest.mark.parametrize("report_id", HAND_CHECKED)
def test_real_records_match_the_hand_checked_reports(
    real_records: dict[str, ServiceRecord], report_id: str
) -> None:
    expected = HAND_CHECKED[report_id]
    record = real_records[report_id]

    assert {field: getattr(record, field) for field in expected} == expected


def test_real_records_have_the_hand_counted_cost_statuses(
    real_records: dict[str, ServiceRecord],
) -> None:
    statuses = Counter(record.cost_status for record in real_records.values())

    assert statuses == {
        CostStatus.ITEMIZED: 13,
        CostStatus.CUT_OFF: 1,
        CostStatus.TOTAL_ONLY: 16,
        CostStatus.NOT_STATED: 20,
    }


@pytest.mark.parametrize(("flag", "report_ids"), HAND_FLAGGED.items())
def test_real_records_flag_exactly_the_reports_found_by_hand(
    real_records: dict[str, ServiceRecord], flag: Flag, report_ids: set[str]
) -> None:
    assert {record.report_id for record in real_records.values() if flag in record.flags} == (
        report_ids
    )


def test_real_records_mark_weekends_and_emergencies_only_where_the_reports_say_so(
    real_records: dict[str, ServiceRecord],
) -> None:
    weekends = {record.report_id for record in real_records.values() if record.weekend}
    emergencies = {record.report_id for record in real_records.values() if record.emergency}

    # Ten more visits fall on a Saturday or Sunday, but their reports neither say so nor charge it.
    assert weekends == {"FSR-0019", "FSR-0022"}
    assert emergencies == {"FSR-0011", "FSR-0013", "FSR-0042"}


def test_real_records_file_every_pf_ds_cloth_change_under_that_job(
    real_records: dict[str, ServiceRecord],
) -> None:
    cloth_jobs = {
        record.report_id
        for record in real_records.values()
        if record.equipment == Equipment.LAROX_PF_DS
        and JobType.FILTER_CLOTH_REPLACEMENT in record.job_types
    }

    assert cloth_jobs == PF_DS_CLOTH_JOBS
