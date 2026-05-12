from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

from pydantic import ValidationError

from semicon_agent.models import AgentPlan, ToolResult
from semicon_agent.tools.base import ToolSpec


class OpenModelLLM:
    """OpenAI-compatible chat-completions adapter for open-model APIs."""

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key or os.getenv("OPEN_MODEL_API_KEY")
        self.timeout = timeout

    def plan(
        self,
        user_request: str,
        tools: list[ToolSpec],
        context: dict[str, object],
    ) -> AgentPlan:
        tool_specs = [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            }
            for tool in tools
        ]
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a semiconductor data-analysis planning agent. "
                    "Return only JSON matching this schema: "
                    '{"reasoning": "short string", "tool_calls": '
                    '[{"name": "tool_name", "arguments": {}}], '
                    '"final_answer": null}. Use available tools only.'
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "request": user_request,
                        "context": context,
                        "available_tools": tool_specs,
                    },
                    ensure_ascii=True,
                    default=str,
                ),
            },
        ]
        content = self._chat(messages, temperature=0.0)
        try:
            return AgentPlan.model_validate_json(_extract_json(content))
        except (ValidationError, ValueError):
            return AgentPlan(
                reasoning="Model did not return a valid plan JSON.",
                final_answer=content,
            )

    def synthesize(
        self,
        user_request: str,
        tool_results: list[ToolResult],
        context: dict[str, object],
    ) -> str:
        result_payload = [result.model_dump() for result in tool_results]
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a semiconductor data-analysis assistant. "
                    "Explain results clearly, cite key numbers, and flag risks. "
                    "Do not invent data that is not present in tool results."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "request": user_request,
                        "context": context,
                        "tool_results": result_payload,
                    },
                    ensure_ascii=True,
                    default=str,
                ),
            },
        ]
        return self._chat(messages, temperature=0.2)

    def _chat(self, messages: list[dict[str, str]], temperature: float) -> str:
        body = json.dumps(
            {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            method="POST",
            headers=self._headers(),
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Open-model API returned HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Open-model API request failed: {exc}") from exc

        try:
            return payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Unexpected open-model API response: {payload}") from exc

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers


def _extract_json(text: str) -> str:
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found.")
    return text[start : end + 1]
