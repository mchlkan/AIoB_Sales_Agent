from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

import requests

from src.config import Settings
from src.schemas import AttemptType, ModelAttempt, ModelTask


class LLMError(RuntimeError):
    pass


@dataclass(frozen=True)
class LLMResponse:
    text: str
    provider: str
    model: str
    task: ModelTask
    fallback_used: bool = False
    repair_used: bool = False
    prompt_version: str | None = None
    latency_ms: int = 0
    attempts: list[ModelAttempt] | None = None


T = TypeVar("T")


TASK_DEFAULT_PROVIDERS: dict[ModelTask, str] = {
    "extraction": "gemini",
    "critique": "groq",
    "crm_chat": "gemini",
}

PROVIDER_FALLBACKS = {
    "gemini": "groq",
    "groq": "gemini",
}

PROMPT_VERSIONS = {
    "extraction": "extraction_v1",
    "critique": "critic_v1",
    "crm_chat": "crm_chat_v1",
    "json_repair": "json_repair_v1",
}


class LLMClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def complete(
        self,
        prompt: str,
        task: ModelTask = "extraction",
        preferred_provider: str | None = None,
        json_mode: bool = True,
        prompt_version: str | None = None,
    ) -> LLMResponse:
        providers = self._provider_order(task, preferred_provider)
        errors: list[str] = []
        attempts: list[ModelAttempt] = []
        for index, provider in enumerate(providers):
            attempt_type: AttemptType = "primary" if index == 0 else "provider_fallback"
            try:
                response = self._complete_with_attempt(
                    prompt,
                    provider,
                    task,
                    json_mode,
                    attempt_type,
                    prompt_version or PROMPT_VERSIONS[task],
                )
                attempts.extend(response.attempts or [])
                return LLMResponse(
                    text=response.text,
                    provider=response.provider,
                    model=response.model,
                    task=task,
                    fallback_used=index > 0,
                    prompt_version=prompt_version or PROMPT_VERSIONS[task],
                    latency_ms=sum(attempt.latency_ms for attempt in attempts),
                    attempts=attempts,
                )
            except LLMError as exc:
                attempts.append(
                    ModelAttempt(
                        task=task,
                        provider=provider,
                        model=self._provider_model(provider),
                        attempt_type=attempt_type,
                        success=False,
                        latency_ms=0,
                        prompt_version=prompt_version or PROMPT_VERSIONS[task],
                        error=str(exc),
                    )
                )
                errors.append(f"{provider}: {exc}")
        raise LLMError("; ".join(errors) or f"No provider configured for task {task}.")

    def complete_json_validated(
        self,
        prompt: str,
        task: ModelTask,
        preferred_provider: str,
        validator: Callable[[dict[str, Any]], T],
        prompt_version: str,
    ) -> tuple[T, LLMResponse]:
        providers = self._provider_order(task, preferred_provider)
        attempts: list[ModelAttempt] = []
        errors: list[str] = []

        for index, provider in enumerate(providers):
            attempt_type: AttemptType = "primary" if index == 0 else "provider_fallback"
            try:
                response = self._complete_with_attempt(
                    prompt, provider, task, True, attempt_type, prompt_version
                )
                attempts.extend(response.attempts or [])
                parsed = self._validate_response(response.text, validator, attempts)
                return parsed, self._response_with_metadata(response, attempts, prompt_version)
            except LLMError as exc:
                attempts.append(
                    ModelAttempt(
                        task=task,
                        provider=provider,
                        model=self._provider_model(provider),
                        attempt_type=attempt_type,
                        success=False,
                        prompt_version=prompt_version,
                        error=str(exc),
                    )
                )
                errors.append(f"{provider}: {exc}")
                continue
            except ValueError as exc:
                errors.append(f"{provider}: {exc}")
                try:
                    repair = self._repair_json(prompt, response.text, str(exc), provider, task)
                    attempts.extend(repair.attempts or [])
                    parsed = self._validate_response(repair.text, validator, attempts)
                    response = LLMResponse(
                        text=repair.text,
                        provider=repair.provider,
                        model=repair.model,
                        task=task,
                        fallback_used=index > 0,
                        repair_used=True,
                    )
                    return parsed, self._response_with_metadata(response, attempts, prompt_version)
                except LLMError as repair_exc:
                    attempts.append(
                        ModelAttempt(
                            task=task,
                            provider=provider,
                            model=self._provider_model(provider),
                            attempt_type="repair",
                            success=False,
                            prompt_version=PROMPT_VERSIONS["json_repair"],
                            error=str(repair_exc),
                        )
                    )
                    errors.append(f"{provider} repair: {repair_exc}")
                except ValueError as repair_exc:
                    errors.append(f"{provider} repair: {repair_exc}")

        raise LLMError("; ".join(errors) or f"No provider configured for task {task}.")

    def _provider_order(self, task: ModelTask, preferred_provider: str | None) -> list[str]:
        candidates = [
            preferred_provider,
            TASK_DEFAULT_PROVIDERS[task],
            self.settings.model_provider if self.settings.model_provider in PROVIDER_FALLBACKS else None,
        ]
        for provider in list(candidates):
            if provider in PROVIDER_FALLBACKS:
                candidates.append(PROVIDER_FALLBACKS[provider])
        ordered: list[str] = []
        for provider in candidates:
            if provider and provider in PROVIDER_FALLBACKS and provider not in ordered:
                ordered.append(provider)
        return ordered

    def _complete_with_attempt(
        self,
        prompt: str,
        provider: str,
        task: ModelTask,
        json_mode: bool,
        attempt_type: AttemptType,
        prompt_version: str,
    ) -> LLMResponse:
        start = time.perf_counter()
        try:
            response = self._complete_with_provider(prompt, provider, task, json_mode)
        except LLMError as exc:
            latency_ms = int((time.perf_counter() - start) * 1000)
            raise LLMError(str(exc)) from exc
        latency_ms = int((time.perf_counter() - start) * 1000)
        attempt = ModelAttempt(
            task=task,
            provider=response.provider,
            model=response.model,
            attempt_type=attempt_type,
            success=True,
            latency_ms=latency_ms,
            prompt_version=prompt_version,
        )
        return LLMResponse(
            text=response.text,
            provider=response.provider,
            model=response.model,
            task=task,
            prompt_version=prompt_version,
            latency_ms=latency_ms,
            attempts=[attempt],
        )

    def _repair_json(
        self,
        original_prompt: str,
        bad_text: str,
        error: str,
        provider: str,
        task: ModelTask,
    ) -> LLMResponse:
        repair_prompt = f"""
You are repairing a JSON response for RepLog AI.

Return only valid JSON that satisfies the original requested schema.
Do not add markdown or commentary.

Original prompt:
{original_prompt}

Invalid response:
{bad_text}

Parser or schema error:
{error}
""".strip()
        return self._complete_with_attempt(
            repair_prompt,
            provider,
            task,
            True,
            "repair",
            PROMPT_VERSIONS["json_repair"],
        )

    @staticmethod
    def _validate_response(
        text: str,
        validator: Callable[[dict[str, Any]], T],
        attempts: list[ModelAttempt],
    ) -> T:
        try:
            return validator(extract_json_object(text))
        except Exception as exc:
            if attempts:
                attempts[-1].success = False
                attempts[-1].error = str(exc)
            raise ValueError(str(exc)) from exc

    @staticmethod
    def _response_with_metadata(
        response: LLMResponse,
        attempts: list[ModelAttempt],
        prompt_version: str,
    ) -> LLMResponse:
        return LLMResponse(
            text=response.text,
            provider=response.provider,
            model=response.model,
            task=response.task,
            fallback_used=any(attempt.attempt_type == "provider_fallback" and attempt.success for attempt in attempts),
            repair_used=any(attempt.attempt_type == "repair" and attempt.success for attempt in attempts),
            prompt_version=prompt_version,
            latency_ms=sum(attempt.latency_ms for attempt in attempts),
            attempts=attempts,
        )

    def _provider_model(self, provider: str) -> str:
        if provider == "gemini":
            return self.settings.gemini_model
        if provider == "groq":
            return self.settings.groq_model
        return provider

    def _complete_with_provider(
        self, prompt: str, provider: str, task: ModelTask, json_mode: bool
    ) -> LLMResponse:
        if provider == "gemini":
            return self._gemini(prompt, task, json_mode)
        if provider == "groq":
            return self._openai_compatible(
                prompt=prompt,
                url="https://api.groq.com/openai/v1/chat/completions",
                api_key=self.settings.groq_api_key,
                model=self.settings.groq_model,
                provider="groq",
                task=task,
                json_mode=json_mode,
            )
        raise LLMError(f"Unsupported MODEL_PROVIDER: {provider}")

    def _gemini(self, prompt: str, task: ModelTask, json_mode: bool) -> LLMResponse:
        if not self.settings.gemini_api_key:
            raise LLMError("GEMINI_API_KEY is not configured.")
        model = self.settings.gemini_model
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            f"?key={self.settings.gemini_api_key}"
        )
        generation_config: dict[str, Any] = {"temperature": 0.1}
        if json_mode:
            generation_config["response_mime_type"] = "application/json"
        payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": generation_config}
        data = self._post_json(url, payload)
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as exc:
            raise LLMError(f"Unexpected Gemini response: {data}") from exc
        return LLMResponse(text=text, provider="gemini", model=model, task=task)

    def _openai_compatible(
        self,
        prompt: str,
        url: str,
        api_key: str,
        model: str,
        provider: str,
        task: ModelTask,
        json_mode: bool,
    ) -> LLMResponse:
        if not api_key:
            raise LLMError(f"{provider.upper()} API key is not configured.")
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "Return only valid JSON. No markdown."
                    if json_mode
                    else "Answer clearly using only the provided context.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        try:
            data = self._post_json(url, payload, headers=headers)
        except LLMError:
            if not json_mode:
                raise
            payload.pop("response_format", None)
            data = self._post_json(url, payload, headers=headers)
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise LLMError(f"Unexpected {provider} response: {data}") from exc
        return LLMResponse(text=text, provider=provider, model=model, task=task)

    @staticmethod
    def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=45)
            if response.status_code >= 400:
                raise LLMError(f"{response.status_code} response: {response.text[:500]}")
            return response.json()
        except (requests.RequestException, json.JSONDecodeError) as exc:
            raise LLMError(str(exc)) from exc


def extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.removeprefix("json").strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("No JSON object found in model response.")
    return json.loads(cleaned[start : end + 1])
