from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import requests

from src.config import Settings
from src.schemas import ModelTask


class LLMError(RuntimeError):
    pass


@dataclass(frozen=True)
class LLMResponse:
    text: str
    provider: str
    model: str
    task: ModelTask
    fallback_used: bool = False


TASK_DEFAULT_PROVIDERS: dict[ModelTask, str] = {
    "extraction": "gemini",
    "critique": "groq",
    "crm_chat": "gemini",
}

PROVIDER_FALLBACKS = {
    "gemini": "groq",
    "groq": "gemini",
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
    ) -> LLMResponse:
        providers = self._provider_order(task, preferred_provider)
        errors: list[str] = []
        for index, provider in enumerate(providers):
            try:
                response = self._complete_with_provider(prompt, provider, task, json_mode)
                return LLMResponse(
                    text=response.text,
                    provider=response.provider,
                    model=response.model,
                    task=task,
                    fallback_used=index > 0,
                )
            except LLMError as exc:
                errors.append(f"{provider}: {exc}")
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
