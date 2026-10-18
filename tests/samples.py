"""Small hand-made data shared by the tests."""

from typing import Any

from sales_assistant.service_records import (
    CostLine,
    CostStatus,
    Equipment,
    JobType,
    LineKind,
    ReportReading,
    ServiceRecord,
)

# What any report says about its visit: a weekday PF-DS cloth change in Sweden.
VISIT: dict[str, Any] = {
    "customer": "Boliden AB",
    "site": "Aitik",
    "country": "Sweden",
    "visit_date": "2023-05-12",
    "equipment": Equipment.LAROX_PF_DS,
    "job_types": [JobType.FILTER_CLOTH_REPLACEMENT],
    "weekend": False,
    "emergency": False,
    "customer_parts": False,
}
LINES = [
    CostLine(description="Travel", kind=LineKind.TRAVEL, quantity=4.9, unit_price=62, amount=303.8),
    CostLine(description="Labour", kind=LineKind.LABOUR, quantity=8.4, unit_price=78, amount=655.2),
    CostLine(description="Cloths", kind=LineKind.PART, quantity=12, unit_price=98, amount=1176),
]


def make_reading(**changes: Any) -> ReportReading:
    """A clean, itemized reading of the visit; a test changes what it needs."""
    fields = VISIT | {
        "on_site_hours": 8.4,
        "travel_hours": 4.9,
        "task_hours": [2.75, 5.65],
        "currency": "EUR",
        "cost_lines": LINES,
        "total": 2135.0,
        "vat": None,
    }
    return ReportReading(**(fields | changes))


def make_record(report_id: str, **changes: Any) -> ServiceRecord:
    """A record of the visit, in EUR, with no cost lines; a test sets the rates it needs."""
    fields = VISIT | {
        "report_id": report_id,
        "on_site_hours": 8.0,
        "travel_hours": 4.0,
        "task_hours": [],
        "currency": "EUR",
        "cost_lines": [],
        "total": None,
        "vat": None,
        "cost_status": CostStatus.NOT_STATED,
        "total_ex_vat": None,
        "labour_rate": None,
        "travel_rate": None,
        "flags": [],
    }
    return ServiceRecord(**(fields | changes))
