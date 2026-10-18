"""Small hand-made data shared by the tests."""

from pathlib import Path
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


# A tiny plant: silica rises from 1 to 8% hour by hour while air flow falls and amine rises.
# Its four March hours and four April hours are two days apart, and its density never moves.
PLANT_CSV = """\
date,% Iron Feed,Flotation Column 01 Air Flow,Amina Flow,Ore Pulp Flow,Ore Pulp Density,\
% Iron Concentrate,% Silica Concentrate
2017-03-30 01:00:00,56,300,460,400,1.7,66.0,1
2017-03-30 02:00:00,55,300,470,401,1.7,65.5,2
2017-03-30 03:00:00,56,290,480,399,1.7,65.0,3
2017-03-30 04:00:00,55,280,490,400,1.7,64.5,4
2017-04-02 01:00:00,56,270,500,401,1.7,64.0,5
2017-04-02 02:00:00,55,260,510,399,1.7,63.5,6
2017-04-02 03:00:00,56,250,520,400,1.7,63.0,7
2017-04-02 04:00:00,55,250,530,401,1.7,62.5,8
"""


def write_plant_csv(path: Path) -> None:
    """Write the tiny plant's hourly data to `path`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(PLANT_CSV, encoding="utf-8")
