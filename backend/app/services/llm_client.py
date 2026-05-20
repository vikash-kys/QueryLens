"""
LLM Client Abstraction
Supports Anthropic Claude and OpenAI GPT-4o.
"""
import json
import re
from typing import Any
import anthropic
import structlog
from app.config import settings

log = structlog.get_logger()

_anthropic_client: anthropic.Anthropic | None = None
_openai_client = None
_gemini_client = None


def _get_anthropic() -> anthropic.Anthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _anthropic_client


def _get_openai():
    global _openai_client
    if _openai_client is None:
        import openai
        _openai_client = openai.OpenAI(api_key=settings.openai_api_key)
    return _openai_client


def _get_gemini():
    global _gemini_client
    if _gemini_client is None:
        import openai
        _gemini_client = openai.OpenAI(
            api_key=settings.gemini_api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
        )
    return _gemini_client


def complete(
    system: str,
    user: str,
    temperature: float = 0.0,
    max_tokens: int = 2048,
    json_mode: bool = False,
) -> str:
    """Send a completion request to the configured LLM provider."""
    if settings.llm_provider == "anthropic":
        return _complete_anthropic(system, user, temperature, max_tokens)
    elif settings.llm_provider == "gemini":
        return _complete_gemini(system, user, temperature, max_tokens, json_mode)
    else:
        return _complete_openai(system, user, temperature, max_tokens, json_mode)


def _complete_anthropic(system: str, user: str, temperature: float, max_tokens: int) -> str:
    client = _get_anthropic()
    response = client.messages.create(
        model=settings.llm_model_anthropic,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return response.content[0].text


def _complete_openai(system: str, user: str, temperature: float, max_tokens: int, json_mode: bool) -> str:
    client = _get_openai()
    kwargs: dict[str, Any] = dict(
        model=settings.llm_model_openai,
        temperature=temperature,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    response = client.chat.completions.create(**kwargs)
    return response.choices[0].message.content


def _complete_gemini(system: str, user: str, temperature: float, max_tokens: int, json_mode: bool) -> str:
    client = _get_gemini()
    kwargs: dict[str, Any] = dict(
        model=settings.llm_model_gemini,
        temperature=temperature,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    response = client.chat.completions.create(**kwargs)
    return response.choices[0].message.content


def parse_json_response(text: str) -> dict:
    """Robustly parse JSON from LLM response (handles markdown fences)."""
    # Strip markdown code fences
    text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("```").strip()
    # Find first { ... } block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group(0)
    return json.loads(text)
