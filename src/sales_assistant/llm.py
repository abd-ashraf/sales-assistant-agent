"""The chat model, and the form-filling calls that ingest makes with it."""

from collections.abc import Callable

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from sales_assistant.config import Settings


def chat_model(settings: Settings) -> ChatOpenAI:
    """Return the OpenAI model named in the settings; it reads OPENAI_API_KEY by itself."""
    return ChatOpenAI(model=settings.openai_model)


def form_filler[Form: BaseModel](model: BaseChatModel, form: type[Form]) -> Callable[[str], Form]:
    """Return a function that has `model` answer a request by filling in `form`."""
    filling_model = model.with_structured_output(form)

    def fill(request: str) -> Form:
        """Send the request, and return the form the model filled in."""
        return form.model_validate(filling_model.invoke(request))

    return fill
