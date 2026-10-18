"""Service cost estimates, built in code from the pieces of past visits.

No past visit matches a new one exactly, so each piece of the budget comes from the records
that know it: hours on site from the same kind of job, labour and travel from visits in the
same country, and part prices from past invoices. The model only chooses the inputs and
explains the result; every number is computed here, and every value names its report.
"""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import product
from math import prod
from statistics import median, quantiles

from pydantic import BaseModel, Field

from sales_assistant.service_records import Equipment, Flag, JobType, LineKind, ServiceRecord

# US dollars per unit of each currency: approximate 2024 averages, named in every estimate.
USD_PER_UNIT = {"USD": 1.0, "EUR": 1.08, "CAD": 0.73, "AUD": 0.66, "SEK": 0.095, "ZAR": 0.055}
DEFAULT_CURRENCY = "USD"
# The likely range drops the cheapest and the dearest tenth of all combinations of past values.
RANGE_SLICES = 10
# A flag is worth a warning only where it touches what the record gives the estimate.
HOURS_FLAG_NOTES = {Flag.HOURS_MISMATCH: "its task hours do not add up to its hours on site"}
MONEY_FLAG_NOTES = {
    Flag.TOTAL_MISMATCH: "its cost lines do not add up to its total",
    Flag.RATE_MISMATCH: "one of its lines is not hours times rate",
    Flag.CURRENCY_ASSUMED: "its '$' was read as US dollars",
}


class PartNeed(BaseModel):
    """A part the job needs, as the salesperson describes it."""

    name: str = Field(
        description="The part in a few words, as an invoice would name it, such as 'filter cloth'."
    )
    quantity: float = Field(gt=0, description="How many the job needs.")


class CostQuestion(BaseModel):
    """What a service cost estimate needs to know."""

    equipment: Equipment
    job_type: JobType
    country: str = Field(description="The country of the customer's site, in English.")
    parts: list[PartNeed] = Field(
        default_factory=list, description="The parts the job needs, if the salesperson says."
    )


@dataclass(frozen=True)
class Piece:
    """One piece of an estimate: its past values, in the estimate's units, and their reports."""

    name: str
    unit: str
    values: tuple[float, ...]
    reports: tuple[str, ...]


@dataclass(frozen=True)
class Term:
    """One part of the total: an amount times a price, such as hours on site times the rate."""

    label: str
    amount: Piece
    price: Piece

    @property
    def typical(self) -> float:
        """The typical amount times the typical price."""
        return median(self.amount.values) * median(self.price.values)

    def possible_totals(self) -> list[float]:
        """Every past amount times every past price."""
        return [amount * price for amount in self.amount.values for price in self.price.values]


@dataclass(frozen=True)
class FoundPieces:
    """The past values found for each piece of a visit; None where the reports have none."""

    hours: Piece | None
    labour_rate: Piece | None
    travel_hours: Piece | None
    travel_rate: Piece | None
    part_prices: tuple[tuple[PartNeed, Piece | None], ...]

    @property
    def gives_a_total(self) -> bool:
        """Whether labour and travel are both known; parts without a price are noted apart."""
        return all((self.hours, self.labour_rate, self.travel_hours, self.travel_rate))

    def found(self) -> tuple[Piece, ...]:
        """Every piece found, in the order an estimate lists them."""
        pieces = (self.hours, self.labour_rate, self.travel_hours, self.travel_rate)
        return tuple(p for p in (*pieces, *(price for _, price in self.part_prices)) if p)

    def money(self) -> tuple[Piece, ...]:
        """The pieces that are amounts of money: the rates and the part prices."""
        prices = (self.labour_rate, self.travel_rate, *(price for _, price in self.part_prices))
        return tuple(piece for piece in prices if piece)

    def terms(self) -> tuple[Term, ...]:
        """The parts of the total whose amount and price are both known."""
        pairs = (
            ("labour", self.hours, self.labour_rate),
            ("travel", self.travel_hours, self.travel_rate),
        )
        terms = [Term(label, amount, price) for label, amount, price in pairs if amount and price]
        terms += [
            Term(f"{need.name} ({need.quantity:g})", _given(need.quantity), price)
            for need, price in self.part_prices
            if price
        ]
        return tuple(terms)


@dataclass(frozen=True)
class Estimate:
    """A cost estimate: its pieces and totals, and what the reports could not give."""

    question: CostQuestion
    currency: str
    found: FoundPieces
    typical: float | None
    likely_range: tuple[float, float] | None
    converted_from: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def reports(self) -> list[str]:
        """Every report behind the estimate, in order."""
        return sorted({report for piece in self.found.found() for report in piece.reports})

    @property
    def combinations(self) -> int:
        """How many combinations of past values the likely range comes from."""
        return prod(len(term.possible_totals()) for term in self.found.terms())


def estimate_visit(records: list[ServiceRecord], question: CostQuestion) -> Estimate:
    """Estimate a planned weekday visit from the pieces of past visits; never fill a gap."""
    # Weekend and emergency visits carry surcharges or unusual work.
    usable = [record for record in records if not record.weekend and not record.emergency]
    local = [r for r in usable if r.country.casefold() == question.country.casefold()]
    currency = _usual_currency(local)
    found = _find_pieces(usable, local, question, currency)
    terms = found.terms()
    totals = [sum(combination) for combination in product(*(t.possible_totals() for t in terms))]
    by_id = {record.report_id: record for record in records}
    hours_records = [by_id[report] for report in (found.hours.reports if found.hours else ())]
    money_records = [by_id[report] for piece in found.money() for report in piece.reports]
    return Estimate(
        question=question,
        currency=currency,
        found=found,
        typical=sum(term.typical for term in terms) if found.gives_a_total else None,
        likely_range=_likely_range(totals) if found.gives_a_total else None,
        converted_from=tuple(
            sorted({r.currency for r in money_records if r.currency and r.currency != currency})
        ),
        warnings=_warnings(hours_records, HOURS_FLAG_NOTES)
        + _warnings(money_records, MONEY_FLAG_NOTES)
        + tuple(
            f"the {piece.name} comes from one report only"
            for piece in found.found()
            if len(piece.values) == 1
        ),
    )


def describe_estimate(estimate: Estimate) -> str:
    """Write the estimate as the text the model reads, with every number already computed."""
    question, found = estimate.question, estimate.found
    lines = [
        f"Service cost estimate in {estimate.currency} for a planned weekday visit: "
        f"{question.job_type} on {question.equipment}, in {question.country}."
    ]
    if estimate.typical is not None and estimate.likely_range is not None:
        low, high = estimate.likely_range
        lines.append(
            f"Typical total: {_money(estimate.typical)}. Likely range: {_money(low)} to "
            f"{_money(high)} (the middle 80% of {estimate.combinations} combinations of past "
            "values)."
        )
        by_term = ", ".join(f"{term.label} {_money(term.typical)}" for term in found.terms())
        lines.append(f"Typical by part of the total: {by_term}.")
    else:
        lines.append("No total: the reports lack labour or travel (see below).")
    lines.append("Pieces from past reports (low / typical / high):")
    lines += [f"- {_spread(piece)} ({', '.join(piece.reports)})" for piece in found.found()]
    for heading, notes in (
        ("Not in the reports", _missing(question, found)),
        ("Assumptions", _assumptions(estimate)),
        ("Warnings", estimate.warnings),
    ):
        if notes:
            lines.append(f"{heading}: " + "; ".join(notes) + ".")
    return "\n".join(lines)


def _find_pieces(
    usable: list[ServiceRecord], local: list[ServiceRecord], question: CostQuestion, currency: str
) -> FoundPieces:
    same_equipment = [record for record in usable if record.equipment == question.equipment]
    same_job = [record for record in same_equipment if question.job_type in record.job_types]
    return FoundPieces(
        hours=_piece("hours on site", "h", ((r, r.on_site_hours) for r in same_job)),
        labour_rate=_piece(
            "labour rate",
            f"{currency}/h",
            ((r, _convert(r.labour_rate, r, currency)) for r in local),
        ),
        travel_hours=_piece("travel time", "h", ((r, r.travel_hours) for r in local)),
        travel_rate=_piece(
            "travel rate",
            f"{currency}/h",
            ((r, _convert(r.travel_rate, r, currency)) for r in local),
        ),
        part_prices=tuple(
            (need, _part_price(need, same_equipment, currency)) for need in question.parts
        ),
    )


def _piece(
    name: str, unit: str, pairs: Iterable[tuple[ServiceRecord, float | None]]
) -> Piece | None:
    known = [(record.report_id, value) for record, value in pairs if value is not None]
    if not known:
        return None
    return Piece(name, unit, tuple(value for _, value in known), tuple(r for r, _ in known))


def _given(quantity: float) -> Piece:
    return Piece("quantity", "", (quantity,), ())


def _part_price(need: PartNeed, records: list[ServiceRecord], currency: str) -> Piece | None:
    """The unit prices of a part on past invoices for the same equipment, converted."""
    prices = (
        (record, _convert(line.unit_price, record, currency))
        for record in records
        for line in record.cost_lines
        if line.kind in (LineKind.PART, LineKind.CONSUMABLE)
        and _names_the_part(line.description, need.name)
    )
    return _piece(f"{need.name}, each", currency, prices)


def _names_the_part(description: str, part: str) -> bool:
    # Every word of the part, without a plural "s", so "filter cloths" finds "Filter Cloth".
    words = [word.removesuffix("s") if len(word) > 3 else word for word in part.lower().split()]
    return all(word in description.lower() for word in words)


def _convert(amount: float | None, record: ServiceRecord, currency: str) -> float | None:
    if amount is None or record.currency not in USD_PER_UNIT:
        return None
    return amount * USD_PER_UNIT[record.currency] / USD_PER_UNIT[currency]


def _usual_currency(records: list[ServiceRecord]) -> str:
    """The currency the country's own reports use most, so the answer reads as they do."""
    counts = Counter(record.currency for record in records if record.currency in USD_PER_UNIT)
    return counts.most_common(1)[0][0] if counts else DEFAULT_CURRENCY


def _likely_range(totals: list[float]) -> tuple[float, float]:
    if len(totals) == 1:
        return totals[0], totals[0]
    cut_points = quantiles(totals, n=RANGE_SLICES, method="inclusive")
    return cut_points[0], cut_points[-1]


def _missing(question: CostQuestion, found: FoundPieces) -> tuple[str, ...]:
    country, equipment = question.country, question.equipment
    gaps = [
        (found.hours, f"no past {question.job_type} job on {equipment}"),
        (found.labour_rate, f"no labour rate for {country}"),
        (found.travel_hours, f"no travel time for {country}"),
        (found.travel_rate, f"no travel rate for {country}"),
    ]
    gaps += [
        (price, f"no invoice price for {need.name} on {equipment}, so it is not in the total")
        for need, price in found.part_prices
    ]
    return tuple(note for piece, note in gaps if piece is None)


def _assumptions(estimate: Estimate) -> tuple[str, ...]:
    notes = [
        "a planned weekday visit: weekend and emergency visits are left out, as they cost more",
        "amounts exclude VAT",
        "hours on site do not grow with the number of parts; parts are priced per unit",
    ]
    if estimate.converted_from:
        currency = estimate.currency
        rates = ", ".join(
            f"1 {code} = {USD_PER_UNIT[code] / USD_PER_UNIT[currency]:.3g} {currency}"
            for code in estimate.converted_from
        )
        notes.append(f"exchange rates are approximate 2024 averages: {rates}")
    return tuple(notes)


def _warnings(records: list[ServiceRecord], notes: dict[Flag, str]) -> tuple[str, ...]:
    """One warning per record and flag that matters, in the order the records were used."""
    warnings = (
        f"{r.report_id}: {notes[flag]}" for r in records for flag in r.flags if flag in notes
    )
    return tuple(dict.fromkeys(warnings))


def _spread(piece: Piece) -> str:
    number = _hours if piece.unit == "h" else _money
    low, typical, high = min(piece.values), median(piece.values), max(piece.values)
    return f"{piece.name}: {number(low)} / {number(typical)} / {number(high)} {piece.unit}"


def _hours(value: float) -> str:
    return f"{value:.1f}"


def _money(value: float) -> str:
    return f"{value:,.0f}" if abs(value) >= 10 else f"{value:.2f}"
