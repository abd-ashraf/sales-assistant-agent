"""Flotation readings compared with one plant's hourly history.

The plant data holds one row per hour: the time, the plant's measurements (feed grade,
reagent flows, air flows, column levels, pulp properties) and the concentrate's iron and
silica. Code works out where a customer's grades rank in that history, which measurements
differed between the plant's good and poor hours, and the data's limits; the model only
phrases the verdict.
"""

import csv
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import pairwise
from pathlib import Path
from statistics import StatisticsError, correlation, median, quantiles

from pydantic import BaseModel, Field

TIME = "date"
IRON = "% Iron Concentrate"
SILICA = "% Silica Concentrate"
# The measurements that moved most with silica; the rest add length, not insight.
MEASUREMENTS_SHOWN = 6
HOUR = timedelta(hours=1)


class FlotationError(Exception):
    """Plant data that is missing or cannot be read."""


class Readings(BaseModel):
    """A customer's concentrate grades."""

    iron_pct: float = Field(ge=0, le=100, description="Iron in the concentrate, in percent.")
    silica_pct: float = Field(ge=0, le=100, description="Silica in the concentrate, in percent.")


@dataclass(frozen=True)
class PlantHistory:
    """The plant's hourly rows: their times, and each column's values in the same order."""

    times: tuple[datetime, ...]
    columns: dict[str, tuple[float, ...]]


@dataclass(frozen=True)
class Grade:
    """Where one reading ranks among the plant's hours."""

    name: str
    value: float
    median: float
    middle_half: tuple[float, float]
    share_as_bad: float


@dataclass(frozen=True)
class Link:
    """How one measurement moved with silica, and its middle value in good and poor hours."""

    name: str
    correlation: float
    good_median: float
    poor_median: float


@dataclass(frozen=True)
class Assessment:
    """A customer's readings set against the plant's history, with the history's limits."""

    readings: Readings
    times: tuple[datetime, ...]
    silica: Grade
    iron: Grade
    both_as_bad: float
    links: tuple[Link, ...]
    monthly_silica: dict[str, float]


def load_history(path: Path) -> PlantHistory:
    """Read the plant's hourly rows from its CSV file."""
    if not path.exists():
        raise FlotationError(f"No plant data at {path}")
    with path.open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    if not rows:
        raise FlotationError(f"No rows in the plant data at {path}")
    names = [name for name in rows[0] if name != TIME]
    return PlantHistory(
        times=tuple(datetime.fromisoformat(row[TIME]) for row in rows),
        columns={name: tuple(float(row[name]) for row in rows) for name in names},
    )


def assess_readings(history: PlantHistory, readings: Readings) -> Assessment:
    """Rank the readings among the plant's hours, and compare its good and poor hours."""
    silica, iron = history.columns[SILICA], history.columns[IRON]
    hours = len(silica)
    # Higher silica is worse, and so is lower iron.
    silica_as_bad = [value >= readings.silica_pct for value in silica]
    iron_as_bad = [value <= readings.iron_pct for value in iron]
    months: dict[str, list[float]] = {}
    for time, value in zip(history.times, silica, strict=True):
        months.setdefault(f"{time:%Y-%m}", []).append(value)
    return Assessment(
        readings=readings,
        times=history.times,
        silica=_grade("silica", readings.silica_pct, silica, sum(silica_as_bad) / hours),
        iron=_grade("iron", readings.iron_pct, iron, sum(iron_as_bad) / hours),
        both_as_bad=sum(s and i for s, i in zip(silica_as_bad, iron_as_bad, strict=True)) / hours,
        links=_links(history),
        monthly_silica={month: median(values) for month, values in months.items()},
    )


def describe_assessment(assessment: Assessment) -> str:
    """Write the assessment as the text the model reads, with every number computed."""
    times = assessment.times
    lines = [
        f"Readings set against one iron ore flotation plant's history: {len(times):,} hourly "
        f"averages from {times[0]:%Y-%m-%d} to {times[-1]:%Y-%m-%d}{_gap(times)}.",
        _ranking(assessment.silica, "high"),
        _ranking(assessment.iron, "low"),
        f"- Both at once: {assessment.both_as_bad:.0%} of hours.",
        "Measurements that moved most with silica (correlation from -1 to 1; then their middle "
        "value in the plant's best quarter of hours by silica, and in its worst quarter):",
    ]
    lines += [
        f"- {link.name}: {link.correlation:+.2f}; {link.good_median:,.2f} in good hours, "
        f"{link.poor_median:,.2f} in poor hours"
        for link in assessment.links
    ]
    monthly = assessment.monthly_silica
    best, worst = min(monthly, key=monthly.__getitem__), max(monthly, key=monthly.__getitem__)
    strongest = max((abs(link.correlation) for link in assessment.links), default=0.0)
    lines.append(
        "Limits: one plant, 2017, hourly averages; each measurement alone links weakly with "
        f"silica (the strongest correlation is {strongest:.2f}); a measurement can differ "
        "because operators reacted to high silica, so these are associations, not causes; "
        f"median silica moved by month from {monthly[best]:.2f}% ({best}) to "
        f"{monthly[worst]:.2f}% ({worst})."
    )
    return "\n".join(lines)


def _grade(name: str, value: float, history: tuple[float, ...], share_as_bad: float) -> Grade:
    quartiles = quantiles(history, n=4, method="inclusive")
    return Grade(name, value, median(history), (quartiles[0], quartiles[2]), share_as_bad)


def _links(history: PlantHistory) -> tuple[Link, ...]:
    """The measurements most linked with silica, strongest first."""
    silica = history.columns[SILICA]
    best_quarter, _, worst_quarter = quantiles(silica, n=4, method="inclusive")
    good = [value <= best_quarter for value in silica]
    poor = [value >= worst_quarter for value in silica]
    links = []
    for name, values in history.columns.items():
        if name in (IRON, SILICA):
            continue
        try:
            strength = correlation(values, silica)
        except StatisticsError:  # a measurement that never changes moves with nothing
            continue
        links.append(
            Link(
                name,
                strength,
                median(v for v, is_good in zip(values, good, strict=True) if is_good),
                median(v for v, is_poor in zip(values, poor, strict=True) if is_poor),
            )
        )
    links.sort(key=lambda link: abs(link.correlation), reverse=True)
    return tuple(links[:MEASUREMENTS_SHOWN])


def _ranking(grade: Grade, worse: str) -> str:
    low, high = grade.middle_half
    return (
        f"- {grade.name.capitalize()} {grade.value:.2f}%: the plant's median is "
        f"{grade.median:.2f}% (middle half of hours {low:.2f} to {high:.2f}%); "
        f"{grade.share_as_bad:.0%} of hours had {grade.name} this {worse} or {worse}er, "
        f"so the reading is worse than {1 - grade.share_as_bad:.0%} of the plant's hours."
    )


def _gap(times: tuple[datetime, ...]) -> str:
    """The longest stretch without data, if any hour is missing."""
    longest = max(pairwise(times), key=lambda pair: pair[1] - pair[0], default=None)
    if longest is None or longest[1] - longest[0] <= HOUR:
        return ""
    return f"; no data from {longest[0]:%Y-%m-%d} to {longest[1]:%Y-%m-%d}"
