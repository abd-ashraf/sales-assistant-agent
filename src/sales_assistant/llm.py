"""The chat model that writes the product cards and runs the agent."""

from langchain_openai import ChatOpenAI

from sales_assistant.config import Settings


def chat_model(settings: Settings) -> ChatOpenAI:
    """Return the OpenAI model named in the settings; it reads OPENAI_API_KEY by itself."""
    return ChatOpenAI(model=settings.openai_model)
