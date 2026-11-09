"""LLM access: Groq (primary) with Gemini (fallback), using the installed `groq` and `google-genai` SDKs.

Both SDK clients are synchronous, so every call runs in a worker thread (asyncio.to_thread) and is
bounded by the SDK timeout plus an outer asyncio timeout: the event loop is never blocked.

Secrets: API keys are SecretStr in settings, handed to the SDK once, and never logged. Failures are
logged as provider name + exception TYPE (+ HTTP status) only, never the exception message, which
could echo request details. Callers get a generic LLMUnavailableError.
"""
import asyncio
import logging
import threading
from typing import Protocol

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class LLMProviderError(Exception):
    """One provider failed. `reason` is safe to log (exception type / status code)."""

    def __init__(self, provider: str, reason: str):
        self.provider = provider
        self.reason = reason
        super().__init__(f"{provider}: {reason}")


class LLMUnavailableError(Exception):
    """No provider could produce an answer (none configured, or all failed)."""


class LLMProvider(Protocol):
    name: str

    async def generate(self, system: str, user: str) -> str: ...


def _describe(exc: BaseException) -> str:
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    return f"{type(exc).__name__}" + (f" (HTTP {status})" if isinstance(status, int) else "")


async def _run_blocking(provider: str, fn, timeout: float, *args) -> str:
    try:
        return await asyncio.wait_for(asyncio.to_thread(fn, *args), timeout=timeout + 5)
    except asyncio.TimeoutError:
        raise LLMProviderError(provider, "timeout") from None
    except Exception as exc:
        raise LLMProviderError(provider, _describe(exc)) from None


class GroqProvider:
    name = "groq"

    def __init__(self, api_key: str, model: str, timeout: float, max_tokens: int, temperature: float,
                 reasoning_effort: str | None = None, base_url: str | None = None):
        from groq import Groq  # imported lazily: only when a Groq key is configured

        options = {"api_key": api_key, "timeout": timeout, "max_retries": 0}  # fail fast -> fall back
        if base_url:
            options["base_url"] = base_url
        self._client = Groq(**options)
        self._model, self._timeout = model, timeout
        self._max_tokens, self._temperature, self._effort = max_tokens, temperature, reasoning_effort

    def _call(self, system: str, user: str) -> str:
        params = {
            "model": self._model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": self._temperature,
            "max_completion_tokens": self._max_tokens,
        }
        if self._effort:
            params["reasoning_effort"] = self._effort
        response = self._client.chat.completions.create(**params)
        return response.choices[0].message.content or ""

    async def generate(self, system: str, user: str) -> str:
        return await _run_blocking(self.name, self._call, self._timeout, system, user)


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str, timeout: float, max_tokens: int, temperature: float,
                 base_url: str | None = None):
        from google import genai
        from google.genai import types

        self._types = types
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=int(timeout * 1000), base_url=base_url),  # timeout is in ms
        )
        self._model, self._timeout = model, timeout
        self._max_tokens, self._temperature = max_tokens, temperature

    def _call(self, system: str, user: str) -> str:
        config = self._types.GenerateContentConfig(
            system_instruction=system, temperature=self._temperature, max_output_tokens=self._max_tokens
        )
        response = self._client.models.generate_content(model=self._model, contents=user, config=config)
        return response.text or ""  # None when blocked / no candidates

    async def generate(self, system: str, user: str) -> str:
        return await _run_blocking(self.name, self._call, self._timeout, system, user)


def _key(secret) -> str | None:
    value = secret.get_secret_value().strip() if secret is not None else ""
    return value or None  # an empty `KEY=` line in .env means "not configured"


def build_providers(settings: Settings) -> list[LLMProvider]:
    """Ordered: Groq (primary), then Gemini (fallback). Providers without a key are skipped."""
    providers: list[LLMProvider] = []
    common = {"timeout": settings.LLM_TIMEOUT_SECONDS, "max_tokens": settings.LLM_MAX_OUTPUT_TOKENS,
              "temperature": settings.LLM_TEMPERATURE}
    if groq_key := _key(settings.GROQ_API_KEY):
        try:
            providers.append(GroqProvider(groq_key, settings.GROQ_MODEL, reasoning_effort=settings.GROQ_REASONING_EFFORT, **common))
        except Exception as exc:
            logger.error("Could not initialise the Groq client: %s", type(exc).__name__)
    if gemini_key := _key(settings.GEMINI_API_KEY):
        try:
            providers.append(GeminiProvider(gemini_key, settings.GEMINI_MODEL, **common))
        except Exception as exc:
            logger.error("Could not initialise the Gemini client: %s", type(exc).__name__)
    return providers


_providers: list[LLMProvider] | None = None
_providers_lock = threading.Lock()


def get_providers() -> list[LLMProvider]:
    global _providers
    if _providers is None:
        with _providers_lock:
            if _providers is None:
                _providers = build_providers(get_settings())
    return _providers


async def generate_answer(system: str, user: str) -> tuple[str, str]:
    """Return (text, provider_name) from the first provider that yields a non-empty answer."""
    providers = get_providers()
    if not providers:
        logger.error("No LLM provider configured: set GROQ_API_KEY and/or GEMINI_API_KEY")
        raise LLMUnavailableError("no provider configured")

    for provider in providers:
        try:
            text = await provider.generate(system, user)
        except LLMProviderError as exc:
            hint = " - model name may be retired or misspelled" if "404" in exc.reason else ""
            logger.warning("LLM provider %s failed: %s%s", provider.name, exc.reason, hint)
            continue
        except Exception as exc:  # defensive: never let one provider's bug skip the fallback
            logger.warning("LLM provider %s failed: %s", provider.name, type(exc).__name__)
            continue
        if text and text.strip():
            return text, provider.name
        logger.warning("LLM provider %s returned an empty response", provider.name)

    raise LLMUnavailableError("all providers failed")
