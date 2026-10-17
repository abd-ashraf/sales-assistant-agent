"""Tests for the model's form-filling calls."""

from pydantic import BaseModel

from sales_assistant.llm import form_filler
from tests.fakes import scripted_model, tool_call


class Answer(BaseModel):
    """A one-field form."""

    product: str


def test_form_filler_returns_the_form_the_model_filled_in() -> None:
    model = scripted_model(tool_call("Answer", product="Larox PF"))

    fill = form_filler(model, Answer)

    assert fill("Which product?") == Answer(product="Larox PF")
    assert model.received[0][0].text == "Which product?"
