"""
LLM Client Abstraction
Supports Anthropic Claude, OpenAI, and Google Gemini (via its OpenAI-compatible endpoint).
"""
import json
import re
import time
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
        _anthropic_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _anthropic_client


def _get_openai() -> openai.OpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = openai.OpenAI(api_key=settings.openai_api_key)
    return _openai_client


def _get_gemini() -> openai.OpenAI:
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = openai.OpenAI(
            api_key=settings.gemini_api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
    return _gemini_client


def complete(system: str, user: str) -> str:
    """Send a completion request to the configured LLM provider."""
    if settings.llm_provider == "anthropic":
        return _complete_anthropic(system, user)
    if settings.llm_provider == "gemini":
        return _complete_chat(_get_gemini(), settings.llm_model_gemini, system, user,
                              reasoning_effort=settings.gemini_reasoning_effort)
    return _complete_chat(_get_openai(), settings.llm_model_openai, system, user)


def _complete_anthropic(system: str, user: str) -> str:
    # Current Claude models think by default and reject non-default temperature:
    # leave room for thinking and read the text block (it is no longer content[0]).
    response = _get_anthropic().beta.messages.create(
        model=settings.llm_model_anthropic,
        max_tokens=16000,
        system=system,
        messages=[{"role": "user", "content": user}],
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("Model declined the request")
    return "".join(block.text for block in response.content if block.type == "text")


def _complete_chat(client: openai.OpenAI, model: str, system: str, user: str, **extra) -> str:
    # No temperature / max_tokens: reasoning models (Gemini 3, GPT-5+) reject or degrade
    # with non-default temperature, and a low token cap gets eaten by thinking tokens.
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                **extra,
            )
            return response.choices[0].message.content or ""
        except openai.RateLimitError as e:
            # Gemini puts the quota window in the error body, not a header: wait out
            # per-minute limits (~1 min), fail fast on daily ones (hours).
            delay = re.search(r"retryDelay\W+(\d+)s", str(e.body))
            if attempt == 2 or not delay or int(delay.group(1)) > 90:
                raise
            log.warning("rate_limited_waiting", seconds=int(delay.group(1)))
            time.sleep(int(delay.group(1)) + 1)


def parse_json_response(text: str) -> dict:
    """Robustly parse JSON from LLM response (handles markdown fences)."""
    # Strip markdown code fences
    text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("```").strip()
    # Find first { ... } block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group(0)
    return json.loads(text)
