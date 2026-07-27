from __future__ import annotations

import json
from typing import Any

import requests

from autorater.config import DEFAULT_JUDGE_MODEL
from autorater.core.utils import clean_text, extract_json_object


class JudgeApiClient:
    def __init__(
        self,
        *,
        api_url: str,
        api_key: str = "",
        judge_model: str = DEFAULT_JUDGE_MODEL,
        timeout_seconds: int = 180,
    ):
        self.api_url = api_url.strip()
        self.api_key = api_key.strip()
        self.judge_model = judge_model.strip() or DEFAULT_JUDGE_MODEL
        self.timeout_seconds = timeout_seconds

    def call_json(self, prompt: str, *, response_schema: dict[str, Any], metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.api_url:
            raise ValueError("API URL is required.")
        if not self.api_key:
            raise ValueError("OpenAI API key is required.")
        payload = self._build_payload(prompt, response_schema=response_schema, metadata=metadata or {})
        headers = {"Content-Type": "application/json"}
        headers["Authorization"] = f"Bearer {self.api_key}"
        response = requests.post(self.api_url, headers=headers, json=payload, timeout=self.timeout_seconds)
        if response.status_code >= 400:
            excerpt = clean_text(response.text, max_chars=1200)
            raise RuntimeError(f"Judge API HTTP {response.status_code}: {excerpt}")
        return self._coerce_response(response)

    def _build_payload(self, prompt: str, *, response_schema: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
        return {
            "model": self.judge_model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a strict JSON-only ML evaluation judge.",
                },
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
        }

    def _coerce_response(self, response: requests.Response) -> dict[str, Any]:
        content_type = response.headers.get("content-type", "")
        parsed: Any
        if "json" in content_type.lower():
            try:
                parsed = response.json()
            except json.JSONDecodeError:
                parsed = response.text
        else:
            parsed = response.text

        if isinstance(parsed, dict):
            direct = self._extract_from_dict(parsed)
            if direct:
                return direct
            return parsed
        if isinstance(parsed, str):
            extracted = extract_json_object(parsed)
            if extracted:
                return extracted
        raise RuntimeError("Judge API response did not contain a JSON object.")

    def _extract_from_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        for key in ("row_evaluations", "score", "dataset_level_summary"):
            if key in data:
                return data
        result = data.get("result")
        if isinstance(result, dict):
            return result
        output_text = data.get("output_text")
        if isinstance(output_text, str):
            extracted = extract_json_object(output_text)
            if extracted:
                return extracted
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0] if isinstance(choices[0], dict) else {}
            message = first.get("message") if isinstance(first.get("message"), dict) else {}
            content = message.get("content") or first.get("text")
            if isinstance(content, str):
                extracted = extract_json_object(content)
                if extracted:
                    return extracted
        output = data.get("output")
        if isinstance(output, list):
            chunks: list[str] = []
            for item in output:
                if not isinstance(item, dict):
                    continue
                for content in item.get("content") or []:
                    if isinstance(content, dict) and isinstance(content.get("text"), str):
                        chunks.append(content["text"])
            if chunks:
                extracted = extract_json_object("\n".join(chunks))
                if extracted:
                    return extracted
        for key in ("content", "text"):
            value = data.get(key)
            if isinstance(value, str):
                extracted = extract_json_object(value)
                if extracted:
                    return extracted
        return {}
