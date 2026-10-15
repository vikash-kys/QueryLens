"""
LLM Client Abstraction
Supports Anthropic Claude, OpenAI, and Google Gemini (via its OpenAI-compatible endpoint).
"""

import json
import re
import anthropic
import openai
import structlog
from app.config import settings

log = structlog.get_logger()

_anthropic_client: anthropic.Anthropic | None = None
_openai_client: openai.OpenAI | None = None
_gemini_client: openai.OpenAI | None = None


def _get_anthropic() -> anthropic.Anthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key, timeout=settings.llm_timeout_seconds, max_retries=0
        )
    return _anthropic_client


def _get_openai() -> openai.OpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = openai.OpenAI(
            api_key=settings.openai_api_key, timeout=settings.llm_timeout_seconds, max_retries=0
        )
    return _openai_client


def _get_gemini() -> openai.OpenAI:
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = openai.OpenAI(
            api_key=settings.gemini_api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            timeout=settings.llm_timeout_seconds,
            max_retries=0,
        )
    return _gemini_client


def complete(system: str, user: str) -> str:
    """Send a completion request to the configured LLM provider."""
    if not getattr(settings, f"{settings.llm_provider}_api_key"):
        raise RuntimeError("Model provider credentials are not configured")
    if not getattr(settings, f"llm_model_{settings.llm_provider}"):
        raise RuntimeError("Model ID is not configured")
    if settings.llm_provider == "anthropic":
        return _complete_anthropic(system, user)
    if settings.llm_provider == "gemini":
        return _complete_chat(
            _get_gemini(),
            settings.llm_model_gemini,
            system,
            user,
            reasoning_effort=settings.gemini_reasoning_effort,
        )
    return _complete_chat(_get_openai(), settings.llm_model_openai, system, user)


def _complete_anthropic(system: str, user: str) -> str:
    # Current Claude models think by default and reject non-default temperature:
    # leave room for thinking and read the text block (it is no longer content[0]).
    response = _get_anthropic().messages.create(
        model=settings.llm_model_anthropic,
        max_tokens=settings.llm_max_output_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    if response.stop_reason in ("refusal", "max_tokens"):
        raise RuntimeError("Model declined the request or returned incomplete output")
    if not response.content:
        raise RuntimeError("Model declined the request")
    return "".join(block.text for block in response.content if block.type == "text")


def _complete_chat(client: openai.OpenAI, model: str, system: str, user: str, **extra) -> str:
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_completion_tokens=settings.llm_max_output_tokens,
        **extra,
    )
    if response.usage:
        log.info(
            "model_token_usage",
            model=model,
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
        )
    if not response.choices or response.choices[0].finish_reason == "length":
        raise ValueError("Model output was incomplete")
    return response.choices[0].message.content or ""


def parse_json_response(text: str) -> dict:
    """Robustly parse JSON from LLM response (handles markdown fences)."""
    # Strip markdown code fences
    text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("```").strip()
    # Find first { ... } block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group(0)
    return json.loads(text)
