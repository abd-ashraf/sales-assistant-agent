"""Service records: each field service report read once into checked fields.

The model copies what a report says into a fixed form; code then works out the cost figures
and flags every gap or mismatch, so a cost estimate never rests on a guess.
"""

import json
import math
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

RECORDS_FILE = "service_records.json"
# Reports read at the same time, one model call each.
PARALLEL_READS = 8
# Smaller differences are rounding: amounts are written to the cent, hours to a tenth.
AMOUNT_TOLERANCE = 1.0
HOURS_TOLERANCE = 0.1
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
# A cost that names no currency, such as "$2,540", is read as US dollars and flagged.
ASSUMED_CURRENCY = "USD"


class RecordError(Exception):
    """Service reports or records that are missing or cannot be read."""


class Equipment(StrEnum):
    """The equipment the reports cover: the brochure products serviced, and the SALA pump."""

    CELLSTATION = "cellstation"
    COLUMNCELL = "columncell"
    CONCORDE_CELL = "concorde_cell"
    FILTER_OPTIMIZER = "filter_optimizer"
    LAROX_PF = "larox_pf"
    LAROX_PF_DS = "larox_pf_ds"
    MD_PUMP = "md_pump"
    ORION_PUMP = "orion_pump"
    SALA_VSP_PUMP = "sala_vsp_pump"
    OTHER = "other"


class JobType(StrEnum):
    """Kinds of work a visit can include; one visit often has several."""

    FILTER_CLOTH_REPLACEMENT = "filter_cloth_replacement"
    FILTER_PLATE_REPLACEMENT = "filter_plate_replacement"
    HYDRAULIC_SERVICE = "hydraulic_service"
    IMPELLER_REPLACEMENT = "impeller_replacement"
    ROTOR_REPLACEMENT = "rotor_replacement"
    ROTOR_STATOR_INSPECTION = "rotor_stator_inspection"
    SEAL_OR_BEARING_SERVICE = "seal_or_bearing_service"
    SPARGER_OR_NOZZLE_SERVICE = "sparger_or_nozzle_service"
    CALIBRATION_OR_SOFTWARE = "calibration_or_software"
    INSTALLATION_OR_COMMISSIONING = "installation_or_commissioning"
    FAULT_REPAIR = "fault_repair"
    INSPECTION_AND_CLEANING = "inspection_and_cleaning"


class LineKind(StrEnum):
    """What a cost line charges for."""

    LABOUR = "labour"
    TRAVEL = "travel"
    PART = "part"
    CONSUMABLE = "consumable"


class CostLine(BaseModel):
    """One row of a report's cost table that charges for something."""

    description: str
    kind: LineKind
    quantity: float | None = Field(description="The quantity or hours as written; null if none.")
    unit_price: float | None = Field(description="The price per unit or hour; null if none.")
    amount: float | None = Field(description="The row's total as written; null if cut off.")


class ReportReading(BaseModel):
    """What one field service report says, copied into fixed fields."""

    customer: str
    site: str
    country: str = Field(description="The country's full English name, such as 'South Africa'.")
    visit_date: str = Field(description="The visit date exactly as written.")
    equipment: Equipment
    job_types: list[JobType] = Field(description="Every kind of work done on the visit.")
    on_site_hours: float | None = Field(
        description="Total hours on site as the report states them ('about 7 hours' is 7; "
        "'6-8h' is 7); null if it gives no single figure, as in '5h plus most of the afternoon'."
    )
    travel_hours: float | None = Field(
        description="Total travel hours for the visit, there and back, stated the same way; "
        "null if not stated or if only one way is given."
    )
    task_hours: list[float] = Field(
        description="The hours on each row of the task table, without its total row; empty "
        "if there is no task table."
    )
    currency: str | None = Field(
        description="The ISO code of the cost's currency when the report names it (a code, a "
        "name or the € sign); null otherwise, including when it shows only '$'."
    )
    cost_lines: list[CostLine] = Field(
        description="The rows of the cost table that charge for something; leave out "
        "subtotal, VAT and total rows."
    )
    total: float | None = Field(
        description="The final total the report states, the amount due, VAT included if the "
        "report adds VAT; null if none is stated."
    )
    vat: float | None = Field(description="The VAT amount the report adds; null if none.")
    weekend: bool = Field(description="True if the visit was at a weekend.")
    emergency: bool = Field(description="True if it was an emergency call-out.")
    customer_parts: bool = Field(description="True if the customer supplied the parts used.")


class CostStatus(StrEnum):
    """How much a report says about its cost."""

    ITEMIZED = "itemized"
    CUT_OFF = "cut_off"
    TOTAL_ONLY = "total_only"
    NOT_STATED = "not_stated"


class Flag(StrEnum):
    """Something in a report that does not add up, or that its reader could not be sure of."""

    TOTAL_MISMATCH = "total_mismatch"
    RATE_MISMATCH = "rate_mismatch"
    VAT_REMOVED = "vat_removed"
    HOURS_MISMATCH = "hours_mismatch"
    CURRENCY_ASSUMED = "currency_assumed"
    DATE_AMBIGUOUS = "date_ambiguous"


class ServiceRecord(ReportReading):
    """A report's reading, with the cost figures and flags that code worked out from it."""

    report_id: str
    cost_status: CostStatus
    total_ex_vat: float | None
    labour_rate: float | None
    travel_rate: float | None
    flags: list[Flag]


ReadReport = Callable[[str], ReportReading]


def read_reports(folder: Path) -> dict[str, str]:
    """Return each report's text by its ID, the file name, in file-name order."""
    paths = sorted(folder.glob("*.txt"))
    if not paths:
        raise RecordError(f"No service reports found in {folder}")
    return {path.stem: path.read_text(encoding="utf-8") for path in paths}


def reading_request(report_id: str, text: str) -> str:
    """Return the request to read one report into the form."""
    return (
        "Fill in the form from this Metso field service report. Copy names, numbers and the "
        "date as the report writes them, and leave a field empty when the report does not "
        "say it: never compute or guess a value.\n\n"
        f"Report {report_id}:\n{text}"
    )


def write_records(
    reports: dict[str, str], read: ReadReport, existing: list[ServiceRecord] | None = None
) -> list[ServiceRecord]:
    """Return one record per report: saved records are kept, the others read in parallel."""
    saved = {record.report_id: record for record in existing or []}
    new_ids = [report_id for report_id in reports if report_id not in saved]

    def read_report(report_id: str) -> ReportReading:
        """Have one report read into the form."""
        return read(reading_request(report_id, reports[report_id]))

    with ThreadPoolExecutor(max_workers=PARALLEL_READS) as pool:
        readings = list(pool.map(read_report, new_ids))
    new = {
        report_id: check_reading(report_id, reading)
        for report_id, reading in zip(new_ids, readings, strict=True)
    }
    return [saved[report_id] if report_id in saved else new[report_id] for report_id in reports]


def check_reading(report_id: str, reading: ReportReading) -> ServiceRecord:
    """Work out the cost figures from a reading, and flag what does not add up or is unclear."""
    total_ex_vat = None if reading.total is None else round(reading.total - (reading.vat or 0), 2)
    cost_status = _cost_status(reading)
    currency_assumed = reading.currency is None and cost_status != CostStatus.NOT_STATED
    return ServiceRecord(
        **reading.model_dump(exclude={"currency"}),
        currency=ASSUMED_CURRENCY if currency_assumed else reading.currency,
        report_id=report_id,
        cost_status=cost_status,
        total_ex_vat=total_ex_vat,
        labour_rate=_rate(reading, LineKind.LABOUR),
        travel_rate=_rate(reading, LineKind.TRAVEL),
        flags=_flags(reading, total_ex_vat, currency_assumed),
    )


def save_records(records: list[ServiceRecord], path: Path) -> None:
    """Write the records to `path` as JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    items = [record.model_dump(mode="json") for record in records]
    text = json.dumps(items, ensure_ascii=False, indent=2)
    path.write_text(text + "\n", encoding="utf-8", newline="\n")


def load_records(path: Path) -> list[ServiceRecord]:
    """Read the records that `save_records` wrote to `path`."""
    if not path.exists():
        raise RecordError(
            f"No service records at {path}: run `sales-assistant ingest` with OPENAI_API_KEY set"
        )
    items = json.loads(path.read_text(encoding="utf-8"))
    try:
        return [ServiceRecord.model_validate(item) for item in items]
    except ValidationError as error:
        raise RecordError(
            f"The service records at {path} are in an older format: "
            "run `sales-assistant ingest --rewrite`"
        ) from error


def _cost_status(reading: ReportReading) -> CostStatus:
    if reading.cost_lines:
        return CostStatus.ITEMIZED if reading.total is not None else CostStatus.CUT_OFF
    return CostStatus.TOTAL_ONLY if reading.total is not None else CostStatus.NOT_STATED


def _rate(reading: ReportReading, kind: LineKind) -> float | None:
    """The hourly rate on the report's first labour or travel line, if it has one."""
    return next((line.unit_price for line in reading.cost_lines if line.kind == kind), None)


def _flags(
    reading: ReportReading, total_ex_vat: float | None, currency_assumed: bool
) -> list[Flag]:
    raised = {
        Flag.TOTAL_MISMATCH: _lines_miss_total(reading.cost_lines, total_ex_vat),
        Flag.RATE_MISMATCH: any(_hours_miss_amount(line) for line in reading.cost_lines),
        Flag.VAT_REMOVED: bool(reading.vat),
        Flag.HOURS_MISMATCH: _tasks_miss_hours(reading.task_hours, reading.on_site_hours),
        Flag.CURRENCY_ASSUMED: currency_assumed,
        # Year first is the only unambiguous form; "08/12/24" could be August or December.
        Flag.DATE_AMBIGUOUS: not ISO_DATE.match(reading.visit_date),
    }
    return [flag for flag, is_raised in raised.items() if is_raised]


def _lines_miss_total(lines: list[CostLine], total_ex_vat: float | None) -> bool:
    """Whether every line has an amount, and the amounts add up to something else."""
    amounts = [line.amount for line in lines if line.amount is not None]
    if total_ex_vat is None or not lines or len(amounts) < len(lines):
        return False
    return not math.isclose(sum(amounts), total_ex_vat, abs_tol=AMOUNT_TOLERANCE)


def _hours_miss_amount(line: CostLine) -> bool:
    """Whether a labour or travel line's hours times its rate differ from its amount."""
    if line.kind not in (LineKind.LABOUR, LineKind.TRAVEL):
        return False
    if line.quantity is None or line.unit_price is None or line.amount is None:
        return False
    return not math.isclose(line.quantity * line.unit_price, line.amount, abs_tol=AMOUNT_TOLERANCE)


def _tasks_miss_hours(task_hours: list[float], on_site_hours: float | None) -> bool:
    """Whether the task table's hours add up to something other than the hours on site."""
    if not task_hours or on_site_hours is None:
        return False
    return not math.isclose(sum(task_hours), on_site_hours, abs_tol=HOURS_TOLERANCE)
