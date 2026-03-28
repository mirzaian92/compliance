from __future__ import annotations

import json
import logging
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.config import Settings
from app.models import AIClassificationResult


log = logging.getLogger(__name__)


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"


def classification_json_schema() -> dict[str, Any]:
    # Keep the schema small + explicit (avoid large Pydantic-generated schemas).
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "is_relevant": {"type": "boolean"},
            "jurisdiction_level": {"type": "string", "enum": ["federal", "state"]},
            "jurisdiction_name": {"type": "string"},
            "state_code": {"type": ["string", "null"]},
            "category": {
                "type": "string",
                "enum": [
                    "bill_introduced",
                    "bill_passed",
                    "final_rule",
                    "proposed_rule",
                    "warning_letter",
                    "recall",
                    "enforcement_action",
                    "agency_notice",
                    "other_regulatory_update",
                ],
            },
            "products": {"type": "array", "items": {"type": "string"}},
            "risk_level": {"type": "string", "enum": ["low", "medium", "high"]},
            "action_needed": {"type": "boolean"},
            "short_summary": {"type": "string"},
            "why_it_matters": {"type": "string"},
            "effective_date": {"type": ["string", "null"]},
            "status_label": {
                "type": "string",
                "enum": ["proposed", "enacted", "effective", "enforcement", "recall", "notice", "unknown"],
            },
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        },
        "required": [
            "is_relevant",
            "jurisdiction_level",
            "jurisdiction_name",
            "state_code",
            "category",
            "products",
            "risk_level",
            "action_needed",
            "short_summary",
            "why_it_matters",
            "effective_date",
            "status_label",
            "confidence",
        ],
    }


def _session(settings: Settings) -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=settings.http_retries,
        backoff_factor=settings.http_backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["POST"],
        raise_on_status=False,
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    return s


def _extract_output_text(payload: dict[str, Any]) -> str:
    # The Responses API can return content under output[].content[].text
    if isinstance(payload.get("output_text"), str) and payload["output_text"].strip():
        return payload["output_text"]

    chunks: list[str] = []
    for item in payload.get("output") or []:
        if not isinstance(item, dict):
            continue
        for c in item.get("content") or []:
            if not isinstance(c, dict):
                continue
            if c.get("type") == "output_text" and isinstance(c.get("text"), str):
                chunks.append(c["text"])
    return "\n".join(chunks).strip()


class OpenAIClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.session = _session(settings)

        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for AI classification")

    def classify_update(self, *, prompt: str) -> AIClassificationResult:
        headers = {
            "Authorization": f"Bearer {self.settings.openai_api_key}",
            "Content-Type": "application/json",
            "User-Agent": self.settings.user_agent,
        }

        # Responses API + Structured Outputs (strict JSON schema)
        req: dict[str, Any] = {
            "model": self.settings.openai_model,
            "input": [
                {
                    "role": "system",
                    "content": (
                        "You are a careful compliance analyst. You must not invent missing facts. "
                        "If uncertain, say unknown and lower confidence. Output must match the provided schema exactly."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "compliance_update",
                    "schema": classification_json_schema(),
                    "strict": True,
                }
            },
            "temperature": 0,
        }

        def _post(request_body: dict[str, Any]) -> dict[str, Any]:
            resp = self.session.post(
                OPENAI_RESPONSES_URL,
                headers=headers,
                json=request_body,
                timeout=self.settings.http_timeout_seconds,
            )
            resp.raise_for_status()
            return resp.json()

        last_err: Exception | None = None
        for attempt in range(1, 3):
            try:
                payload = _post(req)
            except requests.HTTPError as e:
                # Fallback: JSON mode (less strict). Still validated by Pydantic.
                log.warning("OpenAI request failed (attempt=%s); falling back to json_object: %s", attempt, e)
                req["text"]["format"] = {"type": "json_object"}
                req["input"][0]["content"] = (
                    "You are a careful compliance analyst. Output ONLY valid JSON (no markdown). "
                    "Do not invent missing facts. If uncertain, say unknown and lower confidence."
                )
                payload = _post(req)

            out_text = _extract_output_text(payload)
            if not out_text:
                last_err = RuntimeError(f"OpenAI response missing output text: keys={list(payload.keys())}")
            else:
                try:
                    data = json.loads(out_text)
                    return AIClassificationResult.model_validate(data)
                except Exception as e:
                    last_err = e

            # Retry once with a stricter instruction and JSON mode.
            req["text"]["format"] = {"type": "json_object"}
            req["input"][0]["content"] = (
                "Return ONLY a JSON object that matches the required fields. No markdown, no commentary."
            )

        raise RuntimeError(f"OpenAI classification failed after retries: {last_err}")
