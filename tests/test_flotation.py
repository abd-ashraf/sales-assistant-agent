"""Tests for setting flotation readings against a plant's hourly history."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from sales_assistant.flotation import (
    FlotationError,
    PlantHistory,
    Readings,
    assess_readings,
    describe_assessment,
    load_history,
)
from tests.samples import write_plant_csv

REAL_PLANT = Path(__file__).parents[1] / "data" / "flotation_process_data_hourly.csv"
# Silica 7% and iron 63%: two of the tiny plant's eight hours were as bad, its last two.
WORSE_THAN_MOST = Readings(iron_pct=63.0, silica_pct=7.0)


@pytest.fixture(name="history")
def fixture_history(tmp_path: Path) -> PlantHistory:
    """The tiny plant's eight hours."""
    write_plant_csv(tmp_path / "plant.csv")
    return load_history(tmp_path / "plant.csv")


def test_readings_rank_by_the_share_of_hours_at_least_as_bad(history: PlantHistory) -> None:
    assessment = assess_readings(history, WORSE_THAN_MOST)

    assert assessment.silica.share_as_bad == 2 / 8
    assert assessment.iron.share_as_bad == 2 / 8
    assert assessment.both_as_bad == 2 / 8


def test_the_typical_values_are_the_median_and_the_middle_half(history: PlantHistory) -> None:
    silica = assess_readings(history, WORSE_THAN_MOST).silica

    assert silica.median == 4.5
    assert silica.middle_half == (2.75, 6.25)


def test_measurements_are_ranked_by_how_strongly_they_move_with_silica(
    history: PlantHistory,
) -> None:
    links = assess_readings(history, WORSE_THAN_MOST).links

    assert [link.name for link in links[:2]] == ["Amina Flow", "Flotation Column 01 Air Flow"]
    assert links[0].correlation == pytest.approx(1.0)
    assert links[1].correlation < -0.9


def test_good_and_poor_hours_are_the_best_and_worst_quarters_by_silica(
    history: PlantHistory,
) -> None:
    amine = assess_readings(history, WORSE_THAN_MOST).links[0]

    # Good hours had 1 and 2% silica (amine 460, 470); poor hours had 7 and 8% (520, 530).
    assert (amine.good_median, amine.poor_median) == (465, 525)


def test_a_measurement_that_never_changes_is_left_out(history: PlantHistory) -> None:
    links = assess_readings(history, WORSE_THAN_MOST).links

    assert "Ore Pulp Density" not in [link.name for link in links]


def test_the_text_for_the_model_gives_the_ranks_the_links_and_the_limits(
    history: PlantHistory,
) -> None:
    text = describe_assessment(assess_readings(history, WORSE_THAN_MOST))

    assert "8 hourly averages from 2017-03-30 to 2017-04-02; no data from 2017-03-30 to" in text
    assert "- Silica 7.00%: the plant's median is 4.50%" in text
    assert "25% of hours had silica this high or higher, so the reading is worse than 75%" in text
    assert "25% of hours had iron this low or lower, so the reading is worse than 75%" in text
    assert "- Amina Flow: +1.00; 465.00 in good hours, 525.00 in poor hours" in text
    assert "median silica moved by month from 2.50% (2017-03) to 6.50% (2017-04)" in text


def test_readings_must_be_percentages() -> None:
    with pytest.raises(ValidationError):
        Readings(iron_pct=120, silica_pct=3.1)


def test_load_history_names_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FlotationError, match="No plant data"):
        load_history(tmp_path / "plant.csv")


def test_real_plant_ranks_demo_prompt_3_in_its_worst_quarter() -> None:
    if not REAL_PLANT.exists():
        pytest.skip("the assignment data is not in this checkout")
    assessment = assess_readings(load_history(REAL_PLANT), Readings(iron_pct=64.5, silica_pct=3.1))

    assert assessment.silica.share_as_bad == pytest.approx(0.24, abs=0.005)
    assert assessment.iron.share_as_bad == pytest.approx(0.28, abs=0.005)
    assert assessment.both_as_bad == pytest.approx(0.20, abs=0.005)
    assert (assessment.silica.median, assessment.iron.median) == (2.0, 65.21)
    assert assessment.links[0].name == "Flotation Column 01 Air Flow"
